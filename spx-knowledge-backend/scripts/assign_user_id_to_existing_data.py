"""
为现有数据分配 user_id
将 user_id 为 NULL 的记录分配给第一个用户（通常是管理员）
"""

import sys
import io
from pathlib import Path

# 设置标准输出为 UTF-8 编码（Windows 兼容）
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from app.config.settings import settings
import pymysql

def assign_user_id_to_existing_data():
    """为现有数据分配 user_id"""
    try:
        # 从 DATABASE_URL 解析连接信息
        db_url = settings.DATABASE_URL
        if db_url.startswith('mysql+pymysql://'):
            db_url = db_url.replace('mysql+pymysql://', '')
        
        parts = db_url.split('@')
        if len(parts) != 2:
            print(f"❌ 无法解析数据库URL: {db_url}")
            return
        
        user_pass = parts[0].split(':')
        host_db = parts[1].split('/')
        
        if len(user_pass) != 2 or len(host_db) != 2:
            print(f"❌ 无法解析数据库URL: {db_url}")
            return
        
        username = user_pass[0]
        password = user_pass[1]
        host_port = host_db[0].split(':')
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 3306
        database = host_db[1]
        
        print(f"📊 连接数据库: {host}:{port}/{database}")
        
        # 连接数据库
        connection = pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        
        try:
            with connection.cursor() as cursor:
                # 获取第一个用户ID
                cursor.execute("SELECT id FROM users ORDER BY id LIMIT 1")
                result = cursor.fetchone()
                
                if not result:
                    print("❌ 没有找到用户，请先创建用户")
                    return
                
                user_id = result[0]
                print(f"✅ 找到用户ID: {user_id}")
                
                # 更新 documents 表
                cursor.execute("SELECT COUNT(*) FROM documents WHERE user_id IS NULL")
                null_count = cursor.fetchone()[0]
                
                if null_count > 0:
                    print(f"\n📝 更新 documents 表: {null_count} 条记录")
                    cursor.execute("""
                        UPDATE documents 
                        SET user_id = %s 
                        WHERE user_id IS NULL
                    """, (user_id,))
                    affected = cursor.rowcount
                    print(f"✅ 已更新 {affected} 条记录")
                else:
                    print(f"\n✅ documents 表无需更新")
                
                # 更新 knowledge_bases 表
                cursor.execute("SELECT COUNT(*) FROM knowledge_bases WHERE user_id IS NULL")
                null_count = cursor.fetchone()[0]
                
                if null_count > 0:
                    print(f"\n📝 更新 knowledge_bases 表: {null_count} 条记录")
                    cursor.execute("""
                        UPDATE knowledge_bases 
                        SET user_id = %s 
                        WHERE user_id IS NULL
                    """, (user_id,))
                    affected = cursor.rowcount
                    print(f"✅ 已更新 {affected} 条记录")
                else:
                    print(f"\n✅ knowledge_bases 表无需更新")
                
                # 提交事务
                connection.commit()
                print("\n✅ 所有更新已提交")
                
        except Exception as e:
            connection.rollback()
            print(f"❌ 发生错误，已回滚: {e}")
            raise
        finally:
            connection.close()
            print("\n✅ 数据库连接已关闭")
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("为现有数据分配 user_id")
    print("="*60)
    print("\n⚠️  警告：此脚本会将所有 user_id 为 NULL 的记录分配给第一个用户")
    print("   如果这是您想要的操作，请继续。\n")
    
    response = input("是否继续？(yes/no): ")
    if response.lower() in ['yes', 'y']:
        assign_user_id_to_existing_data()
    else:
        print("已取消操作")

