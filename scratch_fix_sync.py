from etl.hist_load import get_conn
c=get_conn()
c.cursor().execute("INSERT INTO sync_logs (type, status, records_processed, last_order_date) VALUES ('delta', 'success', 0, NOW())")
c.commit()
c.close()
