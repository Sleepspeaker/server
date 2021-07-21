import argparse
import os
import sys
import threading
import time
import urllib
import urllib.error
from logging import INFO, StreamHandler, getLogger

import api
import kakomimasu

logger = getLogger(__name__)
logger.addHandler(StreamHandler(sys.stderr))
logger.setLevel(INFO)


def match_manage(token, url, sec):
    client = api.Client(token, url)

    team_id = None
    while team_id is None:
        try:
            me = client.get_team_me()
            team_id = me.data["teamID"]
        except urllib.error.URLError as e:
            logger.info("failed to get /teams/me: %s", e.reason.args[1])
            time.sleep(1)
            continue

    playing = {}
    # マッチの取得
    while True:
        try:
            res = client.get_team_matches(team_id)
        except urllib.error.URLError as e:
            logger.info("failed to connect server: %s", e.reason.args[1])
            logger.info("retry in 5 seconds")
            time.sleep(5)
            continue

        if res.code != 200:
            logger.info("failed to get matches: %s", res.code)
        else:
            for match in res.data["matches"]:
                match_id = match["matchID"]
                # 開始したリストに存在しない試合を開始
                if match_id in playing:
                    continue
                logger.info("spawn ai(match_id=%d)", match_id)
                playing[match_id] = True

                ai = kakomimasu.SampleAI(
                    client,
                    match_id,
                    team_id,
                    match["turns"],
                    match["operationMillis"],
                    match["transitionMillis"],
                )
                # 並列で試合を実行
                threading.Thread(target=ai.run, args=(logger,), daemon=True).start()

        time.sleep(sec)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token", type=str, default=os.getenv("PROCON31_TOKEN"), help="Access Token"
    )
    parser.add_argument(
        "--url", type=str, default=os.getenv("PROCON31_URL"), help="URL"
    )
    parser.add_argument(
        "--sec", type=int, default=5, help="Interval seconds for get matches"
    )

    args = parser.parse_args()

    if args.token is None:
        parser.error("token required")
    if args.url is None:
        parser.error("url required")

    logger.info("token: %s", args.token)
    logger.info("url: %s", args.url)
    try:
        match_manage(args.token, args.url, args.sec)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
