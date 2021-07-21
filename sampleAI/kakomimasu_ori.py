import random
import statistics
import time
import typing
from dataclasses import dataclass

import api

DIR_X = [-1, -1, -1, 0, 0, 1, 1, 1]
DIR_Y = [-1, 0, 1, -1, 1, -1, 0, 1]


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

    def in_bounds(self, pos: Pos):
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

            actions = self._get_random_actions(match)
            self._client.post_action(self._match_id, actions)
            logger.info("[match_id:%d] post actions", self._match_id)

            elapsed = time.time() - match.started_at_unix
            logger.info("[match_id:%d] waiting next operation step ...", self._match_id)
            time.sleep(self._turn_sec - (elapsed % self._turn_sec) + 0.01)

        logger.info("[match_id:%d] end", self._match_id)

    def _get_random_actions(self, match: Match):
        action_to: typing.Set[Pos] = set()

        def to_conflict(action: ActionRequest) -> bool:
            if action.pos in action_to:
                return True
            if action.type == "remove" and action.agent.pos in action_to:
                return True
            return False

        me = match.find_team(self._team_id)
        actions = []
        for agent in me.agents:
            candidates = [
                action
                for action in self._enumerate_actions(match, agent)
                if not to_conflict(action)
            ]
            weights = [
                max(self._eval_weight(match, action), 0) for action in candidates
            ]
            picked = random.choices(candidates, weights=weights, k=5)
            action = max(picked, key=lambda x: self._eval_weight(match, x))

            action_to.add(action.pos)
            if action.type == "remove":
                action_to.add(action.agent.pos)

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

    def _eval_weight(self, match: Match, action: ActionRequest) -> int:
        if action.type == "stay":
            return 1
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

    def _eval_square(self, match: Match, pos: Pos) -> int:
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
