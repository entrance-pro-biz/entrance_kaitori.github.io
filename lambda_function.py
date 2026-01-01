import json
import csv
import urllib.request
import urllib.parse
import os
import boto3
import re

# 環境変数から設定を読み込む
S3_BUCKET = os.environ.get('S3_BUCKET_NAME')
SHEET_ID = os.environ.get('SPREADSHEET_ID')
SHEET_GID = os.environ.get('SPREADSHEET_GID', '0') # デフォルトは0

s3 = boto3.client('s3')

def lambda_handler(event, context):
    print("処理開始: スプレッドシートの読み込み")
    
    # 1. スプレッドシートをCSVとしてダウンロード
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"
    
    try:
        response = urllib.request.urlopen(csv_url)
        lines = [l.decode('utf-8') for l in response.readlines()]
        reader = csv.reader(lines)
        header = next(reader) # ヘッダーをスキップ
        
        # ヘッダー列のインデックス特定（列がズレても大丈夫なように）
        # 想定: [日時, 画像, 名前, 型番, レア, シリーズ, 年, 価格, 枚数, URL]
        try:
            col_idx = {
                'name': 2,    # C列: カード名
                'number': 3,  # D列: 型番
                'rarity': 4,  # E列: レアリティ
                'price': 7,   # H列: 買取価格
                'url': 9      # J列: 元画像URL
            }
        except:
            print("列定義エラー")
            return
            
        cards = []
        
        for i, row in enumerate(reader):
            if len(row) <= 9: continue # データ不足行はスキップ
            
            # データ抽出
            card_name = row[col_idx['name']]
            card_number = row[col_idx['number']]
            card_rarity = row[col_idx['rarity']]
            price_str = row[col_idx['price']]
            drive_url = row[col_idx['url']]
            
            # 価格が入っていないものはスキップ（Webには出さない）
            if not price_str:
                continue

            # 2. 画像のダウンロードとS3アップロード
            # DriveのURLをダウンロード用に変換
            # https://drive.google.com/file/d/XXX/view -> https://drive.google.com/uc?export=download&id=XXX
            file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', drive_url)
            if not file_id_match:
                print(f"画像URL不正: {card_name}")
                continue
                
            file_id = file_id_match.group(1)
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            # S3上のファイル名（型番_レアリティ.jpg）※重複防止のためIDも含めるのがベストだが今回は簡易化
            safe_name = re.sub(r'[^a-zA-Z0-9]', '', card_number + card_rarity)
            s3_image_key = f"images/{safe_name}_{file_id}.jpg"
            
            # S3に既に存在するかチェック（無駄なDLを防ぐ）
            try:
                s3.head_object(Bucket=S3_BUCKET, Key=s3_image_key)
                # print(f"画像スキップ(既存): {card_name}")
            except:
                print(f"画像アップロード中: {card_name}")
                try:
                    # 画像ダウンロード
                    img_data = urllib.request.urlopen(download_url).read()
                    # S3アップロード
                    s3.put_object(
                        Bucket=S3_BUCKET,
                        Key=s3_image_key,
                        Body=img_data,
                        ContentType='image/jpeg'
                        # ACL='public-read' # バケットポリシーで公開しているのでACL不要
                    )
                except Exception as e:
                    print(f"画像アップロード失敗: {e}")
                    continue

            # 3. Web用データの構築
            # S3の公開URL
            s3_url = f"https://{S3_BUCKET}.s3.ap-northeast-1.amazonaws.com/{s3_image_key}"
            
            cards.append({
                "name": card_name,
                "number": card_number,
                "rarity": card_rarity,
                "price": price_str,
                "image": s3_url
            })
            
        # 4. JSONファイルの生成とアップロード
        json_data = json.dumps({"updated_at": "now", "cards": cards}, ensure_ascii=False)
        
        s3.put_object(
            Bucket=S3_BUCKET,
            Key='data.json',
            Body=json_data.encode('utf-8'),
            ContentType='application/json',
            CacheControl='max-age=60' # 1分キャッシュ
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps(f'Success! Processed {len(cards)} cards.')
        }

    except Exception as e:
        print(e)
        return {
            'statusCode': 500,
            'body': json.dumps('Error processing spreadsheet')
        }
