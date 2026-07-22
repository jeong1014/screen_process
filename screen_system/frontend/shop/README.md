# /shop(商品ページ)の画像置き場

`detail_sizeGuide_v26.html` が使う画像をここに置いてください。
リポジトリには入っていないので、**この7枚が無いと商品ページの画像が表示されません**(404)。

```
frontend/shop/
├─ CDIゴルフ.webp
├─ fabric_guide.png
├─ guide.png
└─ detail_photo/
   ├─ DP.jpg
   ├─ SDP.jpg
   ├─ LN.jpg
   └─ 2maiscreen.jpg
```

置いたらブラウザで `/shop` を開き、画像が出るか確認します(サーバー再起動は不要)。

---

## なぜこの場所なのか

`/shop` は URL 上ルート直下なので、HTML の `./detail_photo/DP.jpg` は
`/detail_photo/DP.jpg` と解釈され、どのルートにも当たらず 404 になります。

そこで HTML 側のパスを `/static/shop/...` に直しました。
`/static` は `frontend/` を配信しているので、ここに置けば届きます。

新しく画像を足す時も `/static/shop/ファイル名` の形で書いてください。
