import urllib.error
import urllib.parse
import urllib.request
import json


class Response:
    def __init__(self, code: int, headers: dict, data: dict = None):
        self.code = code
        self.data = data
        self.headers = headers


class Client:
    def __init__(self, token: str, base_url: str, token_header: bool = True):
        self._token = token
        self._base_url = base_url
        self._token_header = token_header

    def _url(self, path: str) -> str:
        return self._base_url + path

    def _create_request(self, url, data: bytes = None) -> urllib.request.Request:
        header = {"Content-Type": "application/json"}
        if self._token_header:
            header["x-api-token"] = self._token
            req = urllib.request.Request(url, data, header)
            return req
        else:
            params = {"token": self._token}
            req = urllib.request.Request(
                "{}?{}".format(url, urllib.parse.urlencode(params)), data, header
            )
            return req

    def get_team_me(self) -> Response:
        req = self._create_request(self._url("/teams/me"))
        return _get_response_by_request(req)

    def get_team_matches(self, team_id) -> Response:
        req = self._create_request(self._url(f"/teams/{team_id}/matches"))
        return _get_response_by_request(req)

    def get_match_by_id(self, match_id) -> Response:
        req = self._create_request(self._url(f"/matches/{match_id}"))
        return _get_response_by_request(req)

    def post_action(self, match_id: int, action: dict) -> Response:
        req = self._create_request(
            self._url(f"/matches/{match_id}/action"), json.dumps(action).encode()
        )
        return _get_response_by_request(req)


def _get_response_by_request(req: urllib.request.Request) -> Response:
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("UTF-8")
            res_json = json.loads(body)
            return Response(res.code, res.info(), res_json)
    except urllib.error.HTTPError as err:
        return Response(err.code, err.info())
