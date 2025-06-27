from flask import Flask, render_template, jsonify, request
import json
import pymssql
import pandas as pd
import matplotlib.pyplot as plt

app = Flask(__name__)

# 資料庫連接設置
def get_data_from_db():
    dividend_query = """
    SELECT
        FORMAT(RecordMonth, 'yyyy-MM') AS 年月,
        SUM(CASE WHEN StoreID = 1 THEN FLOOR(DividendAmount) ELSE 0 END) AS 伸港店,
        SUM(CASE WHEN StoreID = 2 THEN FLOOR(DividendAmount) ELSE 0 END) AS 嶺東店,
        SUM(CASE WHEN StoreID = 3 THEN FLOOR(DividendAmount) ELSE 0 END) AS 大甲店
    FROM DividendRecords
    GROUP BY FORMAT(RecordMonth, 'yyyy-MM')
    ORDER BY 年月;
    """

    initial_query = """
    SELECT StoreID, FLOOR(InitialInvestment) FROM Stores WHERE StoreID IN (1, 2, 3)
    """

    with pymssql.connect(
        server='192.168.0.106',
        user='sa',
        password='wu469711',
        database='invest'
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(dividend_query)
            dividend_rows = cursor.fetchall()

            cursor.execute(initial_query)
            initial_rows = cursor.fetchall()

    # 將 DividendRecords 轉成 DataFrame
    df = pd.DataFrame(dividend_rows, columns=['年月', '伸港店', '嶺東店', '大甲店'])

    # 建立初始投資字典 StoreID->金額
    initial_dict = {row[0]: row[1] for row in initial_rows}

    # 新增一列，年月欄為「初始投資」，三家店初始投資對應填入
    initial_row_df = pd.DataFrame([{
        '年月': '初始投資',
        '伸港店': initial_dict.get(1, 0),
        '嶺東店': initial_dict.get(2, 0),
        '大甲店': initial_dict.get(3, 0),
    }])

    # 把初始投資列放在最前面
    df = pd.concat([initial_row_df, df], ignore_index=True)

    # 計算各店獲利累積和 (從第二列開始計算，因為第一列是初始投資)
    cumsum_df = df.loc[1:, ['伸港店', '嶺東店', '大甲店']].cumsum()

    # 剩餘金額 = 初始投資 - 獲利累積和
    remaining = {}
    for store in ['伸港店', '嶺東店', '大甲店']:
        initial_value = initial_row_df[store].iloc[0]
        last_cumsum = cumsum_df[store].iloc[-1] if not cumsum_df.empty else 0
        remaining[store] = initial_value - last_cumsum

    # 建立剩餘金額列
    remaining_row_df = pd.DataFrame(
        [{
            '年月': '剩餘金額',
            '伸港店': remaining['伸港店'],
            '嶺東店': remaining['嶺東店'],
            '大甲店': remaining['大甲店'],
        }],
        columns=['年月', '伸港店', '嶺東店', '大甲店']
    )

    # 把剩餘金額放在最後一列
    df = pd.concat([df, remaining_row_df], ignore_index=True)

    return df



@app.route('/api/profit/<int:store_id>')
def api_profit(store_id):
    query = """
    SELECT 
        FORMAT(RecordMonth, 'yyyy-MM') AS 年月,
        SUM(FLOOR(DividendAmount)) AS 獲利金額
    FROM DividendRecords
    WHERE StoreID = %s
    GROUP BY FORMAT(RecordMonth, 'yyyy-MM')
    ORDER BY 年月;
    """

    with pymssql.connect(
        server='192.168.0.106',
        user='sa',
        password='wu469711',
        database='invest'
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (store_id,))
            rows = cursor.fetchall()

    dates = [row[0] for row in rows]
    profits = [row[1] for row in rows]

    return jsonify({'dates': dates, 'profits': profits})

# 計算目前回本狀況
@app.route('/api/all_stores_balance')
def all_stores_balance():
    # 各店初始金額設定
    initial_investments = {
        1: 80000,  # 伸港店
        2: 80000,  # 嶺東店
        3: 50000   # 大甲店
    }

    query = """
        SELECT StoreID, FORMAT(RecordMonth, 'yyyy-MM') AS month, FLOOR(DividendAmount) AS profit
        FROM DividendRecords
        WHERE StoreID IN (1,2,3)
        ORDER BY StoreID, RecordMonth ASC
    """

    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    # 用 StoreID 分組資料
    store_data = {1: [], 2: [], 3: []}
    for store_id, month, profit in rows:
        store_data[store_id].append((month, profit))

    result = []

    # 店名對照
    store_names = {1: "伸港店", 2: "嶺東店", 3: "大甲店"}

    # 組合輸出
    for store_id, records in store_data.items():
        initial = initial_investments.get(store_id, 0)
        total_profit = 0

        store_result = []
        store_result.append({"label": f"{store_names[store_id]}初始金額", "value": initial})

        for month, profit in records:
            store_result.append({"label": month, "value": profit})
            total_profit += profit

        remaining = initial - total_profit
        store_result.append({"label": "剩餘金額", "value": remaining})

        result.append({
            "store_id": store_id,
            "store_name": store_names[store_id],
            "data": store_result
        })

    return jsonify(result)



def get_latest_month():
    query = """
    SELECT TOP 1 FORMAT(RecordMonth, 'yyyy-MM') 
    FROM DividendRecords ORDER BY RecordMonth DESC"""
    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else None

# 新增
@app.route('/api/profit/add', methods=['POST'])
def add_profit():
    data = request.json
    store_id = data.get('store_id')
    profit = data.get('profit')

    if not store_id or profit is None:
        return jsonify({'error': 'store_id 和 profit 是必填欄位'}), 400

    latest_month = get_latest_month()
    if not latest_month:
        return jsonify({'error': '找不到最新月份資料'}), 400

    from datetime import datetime
    record_month = datetime.strptime(latest_month + '-01', '%Y-%m-%d').date()

    insert_query = """
    INSERT INTO DividendRecords (StoreID, RecordMonth, DividendAmount)
    VALUES (%s, %s, %s)
    """

    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            # 檢查資料是否已存在
            cursor.execute("""
                SELECT COUNT(*) FROM DividendRecords 
                WHERE StoreID = %s AND FORMAT(RecordMonth, 'yyyy-MM') = %s
            """, (store_id, latest_month))
            exists = cursor.fetchone()[0] > 0

            if exists:
                return jsonify({'error': '該店鋪最新月份資料已存在，無法新增'}), 400

            cursor.execute(insert_query, (store_id, record_month, profit))
        conn.commit()

    return jsonify({'message': '新增成功'})


# 更新
@app.route('/api/profit/update', methods=['POST'])
def update_profit():
    data = request.json
    store_id = data.get('store_id')
    profit = data.get('profit')

    if not store_id or profit is None:
        return jsonify({'error': 'store_id 和 profit 是必填欄位'}), 400

    latest_month = get_latest_month()
    if not latest_month:
        return jsonify({'error': '找不到最新月份資料'}), 400

    update_query = """
    UPDATE DividendRecords
    SET DividendAmount = %s
    WHERE StoreID = %s AND FORMAT(RecordMonth, 'yyyy-MM') = %s
    """

    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            # 確認該資料存在
            cursor.execute("""
                SELECT COUNT(*) FROM DividendRecords 
                WHERE StoreID = %s AND FORMAT(RecordMonth, 'yyyy-MM') = %s
            """, (store_id, latest_month))
            exists = cursor.fetchone()[0] > 0

            if not exists:
                return jsonify({'error': '該店鋪最新月份資料不存在，無法更新'}), 400

            cursor.execute(update_query, (profit, store_id, latest_month))
        conn.commit()

    return jsonify({'message': '更新成功'})


# 刪除
@app.route('/api/profit/delete', methods=['POST'])
def delete_profit():
    data = request.json
    store_id = data.get('store_id')

    if not store_id:
        return jsonify({'error': 'store_id 是必填欄位'}), 400

    latest_month = get_latest_month()
    if not latest_month:
        return jsonify({'error': '找不到最新月份資料'}), 400

    delete_query = """
    DELETE FROM DividendRecords
    WHERE StoreID = %s AND FORMAT(RecordMonth, 'yyyy-MM') = %s
    """

    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            cursor.execute(delete_query, (store_id, latest_month))
        conn.commit()

    return jsonify({'message': '刪除成功'})

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

@app.route('/edit-profit')
def edit_profit():
    return render_template('edit_profit.html')

@app.route('/api/profit/latest/<int:store_id>')
def get_latest_profit(store_id):
    query = """
    SELECT TOP 1 FLOOR(DividendAmount) AS 獲利金額
    FROM DividendRecords
    WHERE StoreID = %s
    ORDER BY RecordMonth DESC
    """
    with pymssql.connect(server='192.168.0.106', user='sa', password='wu469711', database='invest') as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (store_id,))
            row = cursor.fetchone()
            profit = row[0] if row else None
    return jsonify({'profit': profit})


# app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

