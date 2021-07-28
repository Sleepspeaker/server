import random
import statistics
import time
import typing
from dataclasses import dataclass

import api

DIR_X = [-1, -1, -1, 0, 0, 1, 1, 1]
DIR_Y = [-1, 0, 1, -1, 1, -1, 0, 1]

surround_active = [1, 1, 1, 1, 0, 0]
#マッチのidのリストとactiveのリスト作ろうかなぁ
#idをキーにして探索できれば楽なんだけど
#match_idは取れたからリストに入れよう
#match_idを探索していろいろやろう
match_id_list = []
surround_active_list = []


@dataclass(frozen=True)
class Pos:
    x: int
    y: int

    def neighbor(self) -> typing.Iterator["Pos"]:
        return (Pos(x=self.x + dx, y=self.y + dy) for dx, dy in zip(DIR_X, DIR_Y))


def _at(grid: typing.List[typing.List[int]], pos: Pos) -> int:
    return grid[pos.y - 1][pos.x - 1]


@dataclass(frozen=True)
class Agent:
    agent_id: int
    pos: Pos

    @staticmethod
    def from_dict(d: dict) -> "Agent":
        return Agent(agent_id=d["agentID"], pos=Pos(x=d["x"], y=d["y"]),)

    def on_board(self) -> bool:
        return self.pos.x != 0 and self.pos.y != 0


@dataclass(frozen=True)
class Team:
    team_id: int
    agent: int
    agents: typing.List[Agent]

    @staticmethod
    def from_dict(d: dict) -> "Team":
        return Team(
            team_id=d["teamID"],
            agent=d["agent"],
            agents=list(map(Agent.from_dict, d["agents"])),
        )


@dataclass
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

    def all_squares(self) -> typing.Iterator[Pos]:
        return (
            Pos(x=x, y=y)
            for x in range(1, self.width + 1)
            for y in range(1, self.height + 1)
        )

    def find_team(self, team_id) -> Team:
        if self.teams[0].team_id == team_id:
            return self.teams[0]
        else:
            return self.teams[1]

    def in_bounds(self, pos: Pos):#おそらく壁の外ではないかの判定
        return 1 <= pos.x <= self.width and 1 <= pos.y <= self.height

    def can_put(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) in [0, team_id]

    def can_move(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) in [0, team_id]

    def can_remove(self, team_id: int, pos: Pos) -> bool:
        return _at(self.walls, pos) != 0


@dataclass
class ActionRequest:
    type: str
    agent: Agent
    pos: Pos


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

    def run(self, logger):
        while True:
            logger.info("[match_id:%d] fetch match data", self._match_id)
            res = self._client.get_match_by_id(self._match_id)
            if res.code == 425:
                retry_after = int(res.headers["retry-after"])
                logger.info(
                    "[match_id:%d] waiting %ds ...", self._match_id, retry_after
                )
                time.sleep(retry_after + 0.01)
                continue
            if res.code != 200:
                time.sleep(0.5)
                continue
            match = Match.from_dict(res.data)
            if match.turn == self._turns:
                break

            logger.info("[match_id:%d] start %d turn", self._match_id, match.turn)

            actions = self._get_random_actions(match, self._match_id)#おそらくここで行動決定
            print(actions)
            self._client.post_action(self._match_id, actions)
            logger.info("[match_id:%d] post actions", self._match_id)

            elapsed = time.time() - match.started_at_unix
            logger.info("[match_id:%d] waiting next operation step ...", self._match_id)
            time.sleep(self._turn_sec - (elapsed % self._turn_sec) + 0.01)

        logger.info("[match_id:%d] end", self._match_id)

    def _get_random_actions(self, match: Match, match_id):#この関数がランダムだけど行動決めてる
        print("match_idは " + str(match_id))
        
        if((match_id in match_id_list) == False):
            match_id_list.append(match_id)
            print("match_id_listに" + str(match_id) + "を追加しました")
            surround_active_list.append([1, 1, 1, 1, 0, 0])
        

        action_to: typing.Set[Pos] = set()

        def to_conflict(action: ActionRequest) -> bool:#競合確かめる
            if action.pos in action_to:
                return True
            if action.type == "remove" and action.agent.pos in action_to:
                return True
            return False

        me = match.find_team(self._team_id)
        actions = []
        i = 0;#何番目のエージェントか判別用
        for agent in me.agents:
            candidates = [
                action
                for action in self._enumerate_actions(match, agent)
                if not to_conflict(action)
            ]
            weights = [
                max(self._eval_weight(match, action), 0.001) for action in candidates
            ]
            for weight in weights:
                weight += 100

            if agent.on_board():#エージェントがボード上に居たら
                if(surround_active_list[match_id_list.index(match_id)][i] == 1):#まだ囲み途中なら
                    if(i < 2): zone = self._check_zone2(agent.pos)
                    else:      zone = self._check_zone3(agent.pos)
                    
                    ag_x = agent.pos.x
                    ag_y = agent.pos.y

                    #print(str(agent.pos.x) + " " + str(agent.pos.y) + " zone:" + str(zone))
                    if(zone < 100):
                        pos = Pos(x = ag_x, y = ag_y)
                        action = ActionRequest(type="stay", agent=agent, pos=pos)#バグ回避

                        if(zone == 0):
                            pos = Pos(x = ag_x + 1, y = ag_y)
                        elif(zone == 1):
                            pos = Pos(x = ag_x, y = ag_y - 1)
                        elif(zone == 10):
                            pos = Pos(x = ag_x, y = ag_y + 1)
                        elif(zone == 11):
                            pos = Pos(x = ag_x - 1, y = ag_y)
                        
                        if(self._whitch_wall(match, pos) == 0):#壁が無ければ進む
                            action = ActionRequest(type="move", agent=agent, pos=pos)
                        elif(self._whitch_wall(match, pos) == 1):#敵の壁なら壊す
                            action = ActionRequest(type="remove", agent=agent, pos=pos)
                        else:#味方の壁なら内側（斜め前）に行こうとする。内側が自陣なら外に行くようにした
                            if(zone == 0):
                                pos = Pos(x = ag_x + 1, y = ag_y + 1)
                            elif(zone == 1):
                                pos = Pos(x = ag_x + 1, y = ag_y - 1)
                            elif(zone == 10):
                                pos = Pos(x = ag_x - 1, y = ag_y + 1)
                            elif(zone == 11):
                                pos = Pos(x = ag_x - 1, y = ag_y - 1)
                            
                            if(self._whitch_area(match, pos) == 2):#自分の陣地なら囲みをやめてフリーに
                                surround_active_list[match_id_list.index(match_id)][i] = 0
                                print("match" + str(match_id) + "のagent " + str(i) + " 囲み終わりました！")
                                picked = random.choices(candidates, weights=weights, k=5)
                                action = max(picked, key=lambda x : self._eval_weight(match,x))
                            else:#自分の陣地じゃないなら
                                if(self._whitch_wall(match, pos) != 1):#斜め前が敵の壁じゃないなら進む
                                    action = ActionRequest(type="move", agent=agent, pos=pos)
                                else:#敵の壁なら壊す
                                    action = ActionRequest(type="remove", agent=agent, pos=pos)
                    else:
                        picked = random.choices(candidates, weights=weights, k=5)
                        action = max(picked, key=lambda x : self._eval_weight(match,x))
                else:
                    picked = random.choices(candidates, weights = weights, k=5)
                    #Total of weights must be greater than zeroのエラー。評価値が全部0以下だと停止するみたい？例外キャッチしよう
                    action = max(picked, key=lambda x : self._eval_weight(match,x))
                

            else:#いなかったら
                if(i < 4):#一番目のエージェントなら
                    if(i == 0): pos = Pos(x=7,y=2)
                    if(i == 1): pos = Pos(x=17,y=6)
                    if(i == 2): pos = Pos(x=7,y=8)
                    if(i == 3): pos = Pos(x=17,y=12)
                    action = ActionRequest(type="put", agent=agent, pos=pos)
                else:#それ以外はデフォ
                    if(i == 4): pos = Pos(x=3,y=7)
                    if(i == 5): pos = Pos(x=21,y=7)
                    action = ActionRequest(type="put", agent=agent, pos=pos)

            action_to.add(action.pos)
            if action.type == "remove":
                action_to.add(action.agent.pos)

            actions.append(#idは1スタートってわけではない、どこにその行動をするかを座標に入れる
                {
                    "agentID": action.agent.agent_id,
                    "x": action.pos.x,
                    "y": action.pos.y,
                    "type": action.type,
                    "point": self._eval_weight(match, action)
                }
            )
            i += 1

        return {"actions": actions}

#行動を列挙…？
#yield … 書いてあるとこでいったん止める
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

#行動の評価するみたいよ
    def _eval_weight(self, match: Match, action: ActionRequest) -> int:
        if action.type == "stay":
            return -100
        if action.type == "move":
            neighbor = statistics.mean(
                [
                    self._eval_square(match, pos)
                    for pos in action.pos.neighbor()
                    if match.in_bounds(pos)
                ]
            )
            return self._eval_square(match, action.pos) * 1.5 + neighbor
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
        if action.type == "put":
            neighbor = statistics.mean(
                [
                    self._eval_square(match, pos)
                    for pos in action.pos.neighbor()
                    if match.in_bounds(pos)
                ]
            )
            return neighbor


#マスの評価をするみたいよ
    def _eval_square(self, match: Match, pos: Pos) -> int:
        area = _at(match.areas, pos)    # 陣地
        point = _at(match.points, pos)  # 点数
        wall = _at(match.walls, pos)    # 壁

        if not match.in_bounds(pos):
            return 0
        wall = _at(match.walls, pos)
        if wall != 0:
            return 0
        area = _at(match.areas, pos)
        point = _at(match.points, pos)
        if area == 0:
            return point
        if area != self._team_id:
            return point * 2
        else:
            return point * -2
    
    def _whitch_wall(self, match:Match, pos: Pos) -> int:
        wall = _at(match.walls, pos)

        if(wall == 0):
            #print("壁なんてないで")
            return 0
        else:
            if wall != self._team_id:
                #print("相手の壁やで")
                return 1
            else:
                #print("自分の壁やで")
                return 2
    
    def _whitch_area(self, match:Match, pos: Pos) -> int:
        area = _at(match.areas, pos)

        if(area == 0):
            #print("陣地なんてないで")
            return 0
        else:
            if area != self._team_id:
                #print("相手の陣地やで")
                return 1
            else:
                #print("自分の陣地やで")
                return 2

    """
    def _check_zone(self, pos: Pos) -> int:
        ag_x = pos.x
        ag_y = pos.y
        zone_minx = 1
        zone_miny = 1
        zone_maxx = 23
        zone_maxy = 13
        zone_width = zone_maxx - zone_minx + 1
        zone_height = zone_maxy - zone_miny + 1

        zone = 0
        if(ag_y >= zone_height / zone_width * (ag_x - 1) + zone_minx):          zone += 1
        if((ag_y + 1) > (1 + zone_maxy) - zone_height / zone_width * (ag_x - 1)):    zone += 10

        if(ag_y == zone_miny):                       zone = 0
        if(ag_x == zone_maxx):                       zone = 10
        if(ag_y == zone_maxy):                       zone = 11
        if(ag_x == zone_minx and ag_y != zone_miny): zone = 1

        if(ag_x < zone_minx or ag_x > zone_maxx or ag_y < zone_miny or ag_y > zone_maxy):
            zone = 100

        return zone
    """
    def _check_zone2(self, pos: Pos) -> int:
        ag_x = pos.x
        ag_y = pos.y
        zone_minx = 7
        zone_miny = 2
        zone_maxx = 17
        zone_maxy = 6
        zone_width = zone_maxx - zone_minx + 1
        zone_height = zone_maxy - zone_miny + 1

        zone = 0
        if(ag_y >= zone_height / zone_width * (ag_x - 1) + zone_minx):          zone += 1
        if((ag_y + 1) > (1 + zone_maxy) - zone_height / zone_width * (ag_x - 1)):    zone += 10

        if(ag_y == zone_miny):                       zone = 0
        if(ag_x == zone_maxx):                       zone = 10
        if(ag_y == zone_maxy):                       zone = 11
        if(ag_x == zone_minx and ag_y != zone_miny): zone = 1

        if(ag_x < zone_minx or ag_x > zone_maxx or ag_y < zone_miny or ag_y > zone_maxy):
            zone = 100

        return zone
    
    def _check_zone3(self, pos: Pos) -> int:
        ag_x = pos.x
        ag_y = pos.y
        zone_minx = 7
        zone_miny = 8
        zone_maxx = 17
        zone_maxy = 12
        zone_width = zone_maxx - zone_minx + 1
        zone_height = zone_maxy - zone_miny + 1

        zone = 0
        if(ag_y >= zone_height / zone_width * (ag_x - 1) + zone_minx):          zone += 1
        if((ag_y + 1) > (1 + zone_maxy) - zone_height / zone_width * (ag_x - 1)):    zone += 10

        if(ag_y == zone_miny):                       zone = 0
        if(ag_x == zone_maxx):                       zone = 10
        if(ag_y == zone_maxy):                       zone = 11
        if(ag_x == zone_minx and ag_y != zone_miny): zone = 1

        if(ag_x < zone_minx or ag_x > zone_maxx or ag_y < zone_miny or ag_y > zone_maxy):
            zone = 100

        return zone
