# 環境変数
|環境変数名|例|必須かどうか|用途|
|----------|----------|--------|---------|
|`PROCON31_ADMIN_TOKEN` | up1SxhE9|必須ではない|管理者用のtoken(後述)|

#  実行時に指定可能な引数
`procon_server` の起動時には以下の引数が指定できます。

|名前|例|必須かどうか|デフォルト|用途|
|----------|----------|--------|--------|---------|
|c | match_sample.json|必須||試合の情報の入ったjsonファイルのパス|
|l | :8080|必須ではない|:8080|listenするアドレス|
|d | 10s|必須ではない|10s|現在時刻からstart_atまでのデフォルト時間(ms,s,m,h)|

# 試合の始め方
1. 初回起動時は`chmod +x procon_server_darwin`を入力
1. `./procon_server_darwin -c match_01.json -d 10s` のようにしてサーバーを起動します。  
1. 各プログラムから起動したサーバーへ接続してください(リクエストの詳細についてはapiのドキュメント( https://procon31resources.s3-ap-northeast-1.amazonaws.com/index.html )を参照してください)。
1. 指定した時間になると試合が始まります。同時に複数の試合を行いたい場合は `match_example.json` のmatches部分,teams部分の編集を行ってください。


# 試合情報のjsonの各項目の説明
jsonは大きく2つの要素に分かれています。
`teams`が各チームの情報、`matches`が各試合の情報です。
下記に各要素の説明、サンプルとして `match_example.json` を同梱しています。


## teamsでの指定項目
teamsは以下の要素を持つオブジェクトの配列です。
- id: `number`,  チームのidです。
- name: `string`,  チームの名前です。
- token: `string`, チームが使うトークンです。

## matches
matchesは以下の要素を持つオブジェクトの配列です。
- teams: `array<number>`, 試合に参加するチームの配列です。この配列の要素数は2であり、teamsで指定したidである必要があります。
- turns: `number`, 試合のターン数です。
- operationMillis: `number`,  作戦ステップの時間です。単位はミリ秒です。
- transitionMillis: `number`, 遷移ステップの時間です。単位はミリ秒です。
- startedAtUnixTime: `number`, 試合が開始する時間をUnixTimeで指定できます。0の場合はコマンドライン引数で渡したデフォルト時間経過後に開始します。
- points: `array<array<number>>`, 競技ボードの各マスのポイントを表す2次元配列です。
- width: `number`, 競技ボードの横幅です。
- height: `number`, 競技ボードの縦幅です。
- agents: `number`, それぞれのチームが操作するエージェントの数です。

## 管理者用のトークンについて
管理者用のトークンでは各試合の状況が確認できます。
(配布されたサーバーでは一部未実装)

## web tools
https://procon-31.web.app/
試合の作成、試合の操作に使えるtoolがブラウザ上で使用できます。  
(メンテナンス等でつながらないことがあります。)

# Q&A
## サーバーが起動しているかの確認方法
サーバーが正しく起動していれば、起動したアドレスのルートにアクセスすると https://procon-31.web.app/ にリダイレクトされます。
(例として、デフォルトのアドレスで起動した場合はサーバーが正しく起動していれば http://localhost:8080 にアクセスすると https://procon-31.web.app にリダイレクトされます。)

## 不具合/バグを見つけた
サーバーが出力しているログ、そのときのプログラムへのリクエスト等の不具合を開発チームで再現できる情報をgistにはるなどして、twitterのprocon31タグにでも流していただけると対応できる可能性が高まります。


## 諸注意
- apiのドキュメントではリクエスト数に制限がついている旨が記載されていますが、配布されたサーバーではリクエスト数の制限はついていません。
- 配布されたサーバーでは、 `PROCON31_ADMIN_TOKEN` を必要とするいくつかの機能が実装されていません。
