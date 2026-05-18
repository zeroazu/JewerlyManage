# Seller DB - jewerly.db 適配版

這一版是「方案 A」：不轉換資料庫，而是把 Flask 程式改成配合你的 `jewerly.db` 欄位。

## 使用方式

1. 解壓縮專案
2. 把你的 `jewerly.db` 放到跟 `app.py` 同一層
3. 執行：

```powershell
python -m pip install -r requirements.txt
python app.py
```

4. 開啟：

```text
http://127.0.0.1:5000
```

## 重要差異

這版使用你的資料表名稱：

- `CUSTOMER`
- `PRODUCT`
- `MATERIAL_INVENTORY`
- `RECIPE`
- `ORDER`
- `ORDER_DETAIL`

其中 `ORDER` 是 SQL 關鍵字，所以程式裡都使用 `"ORDER"`。

## 注意

你的 `PRODUCT` 是 `iID` 單一主鍵，所以一個 `iID` 只能代表一個尺寸。
如果同一商品有大、中、小三種尺寸，請建立三筆不同的 `iID`。

你的 `MATERIAL_INVENTORY` 沒有 `purchase_quantity` 欄位，所以這版改成手動輸入 `unit_price`。
