from flask import Flask, render_template, jsonify
import json
import pymssql
import pandas as pd
import matplotlib.pyplot as plt

app = Flask(__name__)

# 資料庫連接設置
def get_data_from_db():
    # 連接到 MSSQL 資料庫
    conn = pymssql.connect(
        server='192.168.0.106',
        user='sa',
        password='wu469711',
        database='invest'
    )

    cursor = conn.cursor()

    query = """
    SELECT
        FORMAT(RecordMonth, 'yyyy-MM') AS '年月',
        SUM(CASE WHEN StoreID = 1 THEN FLOOR(DividendAmount) ELSE 0 END) AS '伸港店',
        SUM(CASE WHEN StoreID = 2 THEN FLOOR(DividendAmount) ELSE 0 END) AS '嶺東店',
        SUM(CASE WHEN StoreID = 3 THEN FLOOR(DividendAmount) ELSE 0 END) AS '大甲店'
    FROM DividendRecords
    GROUP BY FORMAT(RecordMonth, 'yyyy-MM')
    ORDER BY '年月';
    """

    # 執行 SQL 查詢
    cursor.execute(query)
    df = cursor.fetchall()  # 獲取所有結果

    # 轉換為 pandas DataFrame
    df = pd.DataFrame(df, columns=['年月', '伸港店', '嶺東店', '大甲店'])

    conn.close()

    return df

# 取得特定店鋪獲利API
@app.route('/api/profit/<int:store_id>')
def api_profit(store_id):
    conn = pymssql.connect(
        server='192.168.0.106',
        user='sa',
        password='wu469711',
        database='invest'
    )
    cursor = conn.cursor()

    query = """
    SELECT 
        FORMAT(RecordMonth, 'yyyy-MM') AS 年月,
        SUM(FLOOR(DividendAmount)) AS 獲利金額
    FROM DividendRecords
    WHERE StoreID = %s
    GROUP BY FORMAT(RecordMonth, 'yyyy-MM')
    ORDER BY 年月;
    """

    cursor.execute(query, (store_id,))
    rows = cursor.fetchall()
    conn.close()

    dates = [row[0] for row in rows]
    profits = [row[1] for row in rows]

    return jsonify({'dates': dates, 'profits': profits})

# 頁面路由設置
@app.route('/')
def index():
    # 獲取資料庫中的數據
    data = get_data_from_db()
    store_data = [
        {'id': 1, 'name': '伸港店'},
        {'id': 2, 'name': '嶺東店'},
        {'id': 3, 'name': '大甲店'}
    ]

    # 將資料傳遞到 HTML 模板
    return render_template('index.html', data=data, stores = store_data)


@app.route('/chart')
def chart():
    return render_template('chart.html')

if __name__ == "__main__":
    app.run(debug=True)
