name: Translate blog to uk/pl/ru

on:
  push:
    branches: [ main ]
    paths:
      - "index.html"
      - "posts/**"
  workflow_dispatch: {}

jobs:
  translate-and-sync:
    runs-on: ubuntu-latest

    # GITHUB_TOKEN будет использоваться только для GitHub Models (перевод),
    # а для пуша в другие репы используем твой GH_BOT_TOKEN (PAT).
    permissions:
      contents: read   # нужно для GitHub Models

    steps:
      - name: Checkout English source repo
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install requests

      - name: Translate and push to language repos
        env:
          # твой PAT, который имеет доступ к devlab-blog / pl / ru
          GH_BOT_TOKEN: ${{ secrets.GH_BOT_TOKEN }}

          REPO_UK: "MiaGorceva/devlab-blog"
          REPO_PL: "MiaGorceva/devlab-blog.pl"
          REPO_RU: "MiaGorceva/devlab-blog.ru"
        run: |
          python .github/scripts/translate_and_push.py
