import random
import statistics
import time
import typing
from dataclasses import dataclass

import api

DIR_X = [-1, -1, -1, 0, 0, 1, 1, 1]
DIR_Y = [-1, 0, 1, -1, 1, -1, 0, 1]


@dataclass(frozen=True)
#座標を管理するクラス
class Pos:
    x: int
    y: int
    
	#指定した座標の周囲8マスを取得
    def neighbor(self) -> typing.Iterator["Pos"]:
        return (Pos(x=self.x + dx, y=self.y + dy) for dx, dy in zip(DIR_X, DIR_Y))

#指定した座標を取得
def _at(grid: typing.List[typing.List[int]], pos: Pos) -> int:
    return grid[pos.y - 1][pos.x - 1]


@dataclass(frozen=True)
#エージェントを管理するクラス
class Agent:
    agent_id: int
    pos: Pos

    @staticmethod
    #エージェントの生成
    def from_dict(d: dict) -> "Agent":
        return Agent(agent_id=d["agentID"], pos=Pos(x=d["x"], y=d["y"]),)
	#エージェントがフィールド上にあるかどうか
    def on_board(self) -> bool:
        return self.pos.x != 0 and self.pos.y != 0


@dataclass(frozen=True)
#チームの管理
class Team:
    team_id: int
    agent: int
    agents: typing.List[Agent]

    @staticmethod
    #チームの生成
    def from_dict(d: dict) -> "Team":
        return Team(
            team_id=d["teamID"],
            agent=d["agent"],
            agents=list(map(Agent.from_dict, d["agents"])),
        )


@dataclass
#試合を管理するクラス
class Match:
    turn: int
    started_at_unix: int
    width: int
    height: int
    teams: typing.List[Team]
    walls: typing.List[typing.List[int]]
    points: typing.List[typing.List[int]]
    areas: typing.List[typing.List[int]]

    @staticmethod
    #試合の生成
    def from_dict(d: dict) -> "Match":
        return Match(
            turn=d["turn"],
            started_at_unix=d["startedAtUnixTime"],
            width=d["width"],
            height=d["height"],
            teams=list(map(Team.from_dict, d["teams"])),
            walls=d["walls"],
            points=d["points"],
            areas=d["areas"],
        )

	#全ての座標を取得
    def all_squares(self) -> typing.Iterator[Pos]:
        return (
            Pos(x=x, y=y)
            for x in range(1, self.width + 1)
            for y in range(1, self.height + 1)
        )
	#チームの情報を返す
    def find_team(self, team_id) -> Team:
        if self.teams[0].team_id == team_id:
            return self.teams[0]
        else:
            return self.teams[1]
	#指定した座標がフィールド上かどうか
    def in_bounds(self, pos: Pos):
        return 1 <= pos.x <= self.width and 1 <= pos.y <= self.height
	#そこにエージェントをおけるかどうか
    def can_put(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) in [0, team_id]
	#そこにエージェントを移動させることができるかどうか
    def can_move(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) in [0, team_id]
	#指定した位置の城壁を取り除けるか
    def can_remove(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) != 0


@dataclass
class ActionRequest:
    type: str
    agent: Agent
    pos: Pos

#ここからAIの中身
class SampleAI:
    def __init__(
        self,
        client: api.Client,
        match_id: int,
        team_id: int,
        turns: int,
        operation_millis: int,
        transition_millis: int,
    ):
        self._client = client
        self._match_id = match_id
        self._team_id = team_id
        self._turns = turns
        self._operation_millis = operation_millis
        self._transition_millis = transition_millis
        self._turn_sec = (operation_millis + transition_millis) / 1000
	
	#試合の進行に関わる関数(ルールの部分)
    def run(self, logger):
        while True:
            logger.info("[match_id:%d] fetch match data", self._match_id)
            res = self._client.get_match_by_id(self._match_id)
            if res.code == 425:
                retry_after = int(res.headers["retry-after"])
                logger.info("[match_id:%d] waiting %ds ...", self._match_id, retry_after)
                time.sleep(retry_after + 0.01)
                continue
            if res.code != 200:
                time.sleep(0.5)
                continue
            match = Match.from_dict(res.data)
            if match.turn == self._turns:
                break

            logger.info("[match_id:%d] start %d turn", self._match_id, match.turn)

            actions = self._get_random_actions(match)
            self._client.post_action(self._match_id, actions)
            logger.info("[match_id:%d] post actions", self._match_id)

            elapsed = time.time() - match.started_at_unix
            logger.info("[match_id:%d] waiting next operation step ...", self._match_id)
            time.sleep(self._turn_sec - (elapsed % self._turn_sec) + 0.01)

        logger.info("[match_id:%d] end", self._match_id)

	#行動の決定
    def _get_random_actions(self, match: Match):
        action_to: typing.Set[Pos] = set()
		
		#自分のエージェント同士の行動が競合するかどうか
        def to_conflict(action: ActionRequest) -> bool:
            if action.pos in action_to:
                return True
            if action.type == "remove" and action.agent.pos in action_to:
                return True
            return False

        me = match.find_team(self._team_id)
        actions = []
        for agent in me.agents:
			#エージェントのできる行動を配列に入れる
            candidates = [action for action in self._enumerate_actions(match, agent) if not to_conflict(action)]#内包表記
            #重み(行動の優先度)を決定して配列に入れる
            weights = [
                max(self._eval_weight(match, action), 0) for action in candidates
            ]
            #ランダム(重みをある程度考慮)で行動を決定
            #重みが0のものは選ばれない(マイナスはなぜか選ばれる)
            picked = random.choices(candidates, weights=weights, k=5)
            action = max(picked, key=lambda x: self._eval_weight(match, x))

            action_to.add(action.pos)
            if action.type == "remove":
                action_to.add(action.agent.pos)
			
			#actions配列に行動の内容を追加
            actions.append(
                {
                    "agentID": action.agent.agent_id,
                    "x": action.pos.x,
                    "y": action.pos.y,
                    "type": action.type,
                }
            )
        return {"actions": actions}

    def _enumerate_actions(
        self, match: Match, agent: Agent
    ) -> typing.Iterator[ActionRequest]:
        yield ActionRequest(type="stay", agent=agent, pos=agent.pos)
        if agent.on_board():
            neighbor = [pos for pos in agent.pos.neighbor() if match.in_bounds(pos)]
            yield from (
                ActionRequest(type="move", agent=agent, pos=pos)
                for pos in neighbor
                if match.can_move(self._team_id, pos)
            )
            yield from (
                ActionRequest(type="remove", agent=agent, pos=pos)
                for pos in neighbor
                if match.can_remove(self._team_id, pos)
            )
        else:
            yield from (
                ActionRequest(type="put", agent=agent, pos=pos)
                for pos in match.all_squares()
                if match.can_put(self._team_id, pos)
            )

	#以下重み付け
    def _eval_weight(self, match: Match, action: ActionRequest) -> int:
		#なにもしない(最弱行動)
        if action.type == "stay":
			#returnで重みを返す
            return 1
        #エージェントを動かす    
        if action.type == "move":
            neighbor = statistics.mean(
                [
                    self._eval_square(match, pos)
                    for pos in action.pos.neighbor()
                    if match.in_bounds(pos)
                ]
            )
            return self._eval_square(match, action.pos) * 1.5 + neighbor
        #相手の城壁の除去
        if action.type == "remove":
            neighbor = statistics.mean(
                [
                    self._eval_square(match, pos)
                    for pos in action.agent.pos.neighbor()
                    if match.in_bounds(pos)
                ]
            )
            wall = _at(match.walls, action.pos)
            point = _at(match.points, action.pos)
            if wall != self._team_id:
                return point + neighbor
            else:
                return -point + neighbor
        #フィールド上に無いエージェントを置く
        if action.type == "put":
            neighbor = statistics.mean(
                [
                    self._eval_square(match, pos)
                    for pos in action.pos.neighbor()
                    if match.in_bounds(pos)
                ]
            )
            return neighbor

    def _eval_square(self, match: Match, pos: Pos) -> int:
		#指定した座標がフィールド上ではなかったら0を返す
        if not match.in_bounds(pos):
            return 0
        wall = _at(match.walls, pos) #城壁
        #城壁があったら0を返す
        if wall != 0:
            return 0
        area = _at(match.areas, pos) #城壁を除いた陣地
        point = _at(match.points, pos) #点数
        #指定した座標が陣地ではなかったら点数をそのまま返す
        if area == 0:
            return point
        #相手の陣地だったら重みを二倍
        if area != self._team_id:
            return point * 2
        #自分の陣地だったら重みを半分
        else:
            return point * -2
