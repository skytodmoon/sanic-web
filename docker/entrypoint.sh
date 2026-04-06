#!/bin/bash
set -e

echo "Starting AIX-DB All-in-One container..."

# 创建必要的目录
mkdir -p /var/log/supervisor /var/log/nginx /var/log/aix-db /var/log/minio /var/log/postgresql /var/run /data
mkdir -p /var/run/postgresql
mkdir -p /docker-entrypoint-initdb.d

# PostgreSQL 数据目录
PGDATA="/var/lib/postgresql/data"
mkdir -p "$PGDATA"

# 确保 PostgreSQL 相关目录权限正确（每次启动都需要）
chown -R postgres:postgres /var/lib/postgresql
chown -R postgres:postgres /var/run/postgresql
chown -R postgres:postgres /var/log/postgresql
chmod 700 "$PGDATA"

# PostgreSQL 数据目录初始化（仅首次）
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Initializing PostgreSQL database..."

    # 初始化数据库
    gosu postgres /usr/lib/postgresql/17/bin/initdb -D "$PGDATA" --encoding=UTF8 --locale=en_US.UTF-8

    # 配置 PostgreSQL 允许本地和网络连接
    echo "host all all 0.0.0.0/0 md5" >> "$PGDATA/pg_hba.conf"
    echo "host all all ::0/0 md5" >> "$PGDATA/pg_hba.conf"
    # 允许本地 trust 连接（用于初始化）
    echo "local all all trust" >> "$PGDATA/pg_hba.conf"

    # 配置监听地址
    echo "listen_addresses = '*'" >> "$PGDATA/postgresql.conf"

    # 启动 PostgreSQL 进行初始配置
    echo "Starting PostgreSQL for initial setup..."
    gosu postgres /usr/lib/postgresql/17/bin/pg_ctl -D "$PGDATA" -w start -o "-c listen_addresses='localhost'"

    # 等待 PostgreSQL 就绪
    until gosu postgres pg_isready -h localhost; do
        echo "Waiting for PostgreSQL to be ready..."
        sleep 1
    done

    # 创建用户和数据库（将 aix_db 设为超级用户以便创建扩展）
    echo "Creating user and database..."
    gosu postgres psql -c "CREATE USER ${POSTGRES_USER:-aix_db} WITH PASSWORD '${POSTGRES_PASSWORD:-1}' SUPERUSER;" 2>/dev/null || echo "User already exists"
    gosu postgres psql -c "ALTER USER ${POSTGRES_USER:-aix_db} WITH SUPERUSER;" 2>/dev/null || true
    gosu postgres psql -c "CREATE DATABASE ${POSTGRES_DB:-aix_db} OWNER ${POSTGRES_USER:-aix_db};" 2>/dev/null || echo "Database already exists"
    gosu postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB:-aix_db} TO ${POSTGRES_USER:-aix_db};"

    # 执行初始化 SQL（使用 postgres 超级用户执行以确保有权限创建扩展）
    if [ -f /docker-entrypoint-initdb.d/init.sql ]; then
        echo "Running init.sql..."
        gosu postgres psql -d "${POSTGRES_DB:-aix_db}" -f /docker-entrypoint-initdb.d/init.sql
    fi

    # 停止 PostgreSQL（supervisor 会重新启动）
    echo "Stopping PostgreSQL after initialization..."
    gosu postgres /usr/lib/postgresql/17/bin/pg_ctl -D "$PGDATA" -m fast -w stop

    echo "PostgreSQL initialization completed."
else
    echo "PostgreSQL data directory already initialized."
fi

# 确保环境变量传递给 supervisor
export PATH="/aix-db/.venv/bin:${PATH}"
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1
export OTEL_PYTHON_CONTEXT=contextvars_context
export SANIC_WORKER_STATE_TTL=120
# 设置 worker 启动超时时间（秒），默认 180 秒
# 在资源受限环境下（如 2CPU 8GB），worker 启动可能需要更长时间
export SANIC_WORKER_STARTUP_TIMEOUT=${SANIC_WORKER_STARTUP_TIMEOUT:-180}

escape_js_string() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e "s/'/\\\\'/g"
}

generate_runtime_config() {
    local runtime_config_file="/usr/share/nginx/html/runtime-config.js"
    local page_agent_flag="${VITE_ENABLE_PAGE_AGENT:-}"

    mkdir -p "$(dirname "$runtime_config_file")"

    if [ -n "$page_agent_flag" ]; then
        local escaped_flag
        escaped_flag=$(escape_js_string "$page_agent_flag")
        cat > "$runtime_config_file" <<EOF
window.__AIX_RUNTIME_CONFIG__ = Object.assign({}, window.__AIX_RUNTIME_CONFIG__, {
  VITE_ENABLE_PAGE_AGENT: '${escaped_flag}',
});
EOF
    else
        cat > "$runtime_config_file" <<'EOF'
window.__AIX_RUNTIME_CONFIG__ = window.__AIX_RUNTIME_CONFIG__ || {};
EOF
    fi

    echo "Generated runtime config at $runtime_config_file"
}

generate_runtime_config

echo "Starting supervisord..."
# 启动 supervisord
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
