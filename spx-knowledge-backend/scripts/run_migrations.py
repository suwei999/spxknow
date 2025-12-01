"""
执行数据库迁移脚本
从.env文件读取数据库配置，执行migrations目录下的SQL脚本
"""

import os
import sys
from pathlib import Path
import pymysql
from dotenv import load_dotenv

# 加载.env文件
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ 已加载环境变量文件: {env_file}")
else:
    print(f"⚠️  未找到.env文件: {env_file}，使用系统环境变量")

# 从环境变量读取数据库配置
def get_db_config():
    """从环境变量读取数据库配置"""
    # 优先使用DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "")
    
    if database_url and database_url.startswith("mysql+pymysql://"):
        # 解析DATABASE_URL: mysql+pymysql://user:password@host:port/database
        url = database_url.replace("mysql+pymysql://", "")
        parts = url.split("@")
        if len(parts) == 2:
            user_pass = parts[0].split(":")
            host_db = parts[1].split("/")
            if len(host_db) == 2:
                host_port = host_db[0].split(":")
                return {
                    "host": host_port[0],
                    "port": int(host_port[1]) if len(host_port) > 1 else 3306,
                    "user": user_pass[0],
                    "password": user_pass[1] if len(user_pass) > 1 else "",
                    "database": host_db[1]
                }
    
    # 使用分项配置
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "user"),
        "password": os.getenv("MYSQL_PASSWORD", "password"),
        "database": os.getenv("MYSQL_DATABASE", "spx_knowledge")
    }

def execute_sql_file(connection, sql_file: Path):
    """执行SQL文件"""
    print(f"\n📄 执行迁移脚本: {sql_file.name}")
    
    try:
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割SQL语句（以分号分隔，忽略注释）
        statements = []
        current_statement = ""
        
        for line in sql_content.split('\n'):
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('--') or line.startswith('#'):
                continue
            
            current_statement += line + '\n'
            
            # 如果行以分号结尾，说明是一个完整的语句
            if line.endswith(';'):
                statements.append(current_statement.strip())
                current_statement = ""
        
        # 执行所有SQL语句
        cursor = connection.cursor()
        success_count = 0
        error_count = 0
        
        for statement in statements:
            if not statement:
                continue
            try:
                cursor.execute(statement)
                success_count += 1
            except Exception as e:
                error_count += 1
                print(f"  ❌ SQL语句执行失败: {str(e)[:100]}")
                print(f"     语句: {statement[:200]}...")
        
        connection.commit()
        cursor.close()
        
        if error_count == 0:
            print(f"  ✅ 成功执行 {success_count} 条SQL语句")
            return True
        else:
            print(f"  ⚠️  成功 {success_count} 条，失败 {error_count} 条")
            return False
            
    except Exception as e:
        print(f"  ❌ 执行失败: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("数据库迁移脚本执行器")
    print("=" * 60)
    
    # 获取数据库配置
    db_config = get_db_config()
    print(f"\n📊 数据库配置:")
    print(f"   主机: {db_config['host']}:{db_config['port']}")
    print(f"   用户: {db_config['user']}")
    print(f"   数据库: {db_config['database']}")
    
    # 连接数据库
    try:
        connection = pymysql.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        print(f"\n✅ 数据库连接成功")
    except Exception as e:
        print(f"\n❌ 数据库连接失败: {e}")
        sys.exit(1)
    
    # 获取migrations目录
    migrations_dir = Path(__file__).parent.parent / "migrations"
    if not migrations_dir.exists():
        print(f"\n❌ migrations目录不存在: {migrations_dir}")
        sys.exit(1)
    
    # 获取所有SQL文件，按文件名排序
    sql_files = sorted(migrations_dir.glob("*.sql"))
    
    if not sql_files:
        print(f"\n⚠️  未找到SQL迁移脚本")
        sys.exit(0)
    
    print(f"\n📁 找到 {len(sql_files)} 个迁移脚本:")
    for sql_file in sql_files:
        print(f"   - {sql_file.name}")
    
    # 询问是否执行
    print(f"\n❓ 是否执行这些迁移脚本？(y/n): ", end="")
    response = input().strip().lower()
    if response not in ['y', 'yes', '是']:
        print("❌ 已取消")
        connection.close()
        sys.exit(0)
    
    # 执行所有迁移脚本
    print(f"\n🚀 开始执行迁移脚本...")
    success_count = 0
    failed_count = 0
    
    for sql_file in sql_files:
        if execute_sql_file(connection, sql_file):
            success_count += 1
        else:
            failed_count += 1
    
    # 关闭连接
    connection.close()
    
    # 输出结果
    print(f"\n" + "=" * 60)
    print(f"迁移完成: 成功 {success_count} 个，失败 {failed_count} 个")
    print("=" * 60)
    
    if failed_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()

