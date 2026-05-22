#!/bin/bash
# =============================================================================
# vLLM 模型服务启动脚本 v3
# =============================================================================
# 3 组并行，每组 TP=2：
#   - 组 A: GPU 0 (3090) + GPU 1 (3080), 端口 8000
#   - 组 B: GPU 4 (3090) + GPU 2 (3080), 端口 8001
#   - 组 C: GPU 5 (3090) + GPU 3 (3080), 端口 8002
#
# 使用方法:
#   bash scripts/start_vllm_servers_v3.sh [start|stop|status]
# =============================================================================

set -e

export CUDA_DEVICE_ORDER=PCI_BUS_ID

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# vLLM 模型配置 - 3组，每组 TP=2
MODEL="Qwen/Qwen2.5-32B-Instruct-AWQ"

# 3 组配置
TP=2
PORT_BASE=8000

# 每组 GPU 配置：1×3090 (24GB) + 1×3080 (20GB)
# 组 A: GPU 0 (3090) + GPU 1 (3080)
# 组 B: GPU 4 (3090) + GPU 2 (3080)
# 组 C: GPU 5 (3090) + GPU 3 (3080)
declare -a GPU_GROUPS=("0,1" "4,2" "5,3")
declare -a PORTS=(8000 8001 8002)
declare -a NAMES=("A" "B" "C")

# 通用配置
QUANTIZATION="awq"
MAX_MODEL_LEN=8192
MAX_NUM_SEQS=64
GPU_MEMORY_UTILIZATION=0.88  # 稍微降低以适应 3080

# =============================================================================
# 辅助函数
# =============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

check_vllm() {
    if ! command -v python &> /dev/null; then
        error "Python 未找到"
        exit 1
    fi
    if ! python -c "import vllm" 2>/dev/null; then
        error "vLLM 未安装"
        exit 1
    fi
}

check_cuda() {
    if ! command -v nvidia-smi &> /dev/null; then
        error "nvidia-smi 未找到"
        exit 1
    fi
    log "检测到的 GPU:"
    nvidia-smi --query-gpu=index,name,memory.total --format=csv
}

# =============================================================================
# 服务控制
# =============================================================================

start_group() {
    local idx=$1
    local gpus=$2
    local port=$3
    local name=$4

    log "启动组 $name (GPU: $gpus, 端口: $port)..."

    export CUDA_VISIBLE_DEVICES="$gpus"

    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL" \
        --quantization "$QUANTIZATION" \
        --tensor-parallel-size $TP \
        --host 0.0.0.0 \
        --port $port \
        --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
        --max-model-len $MAX_MODEL_LEN \
        --max-num-seqs $MAX_NUM_SEQS \
        --trust-remote-code \
        > "$LOG_DIR/vllm_group_${name,,}.log" 2>&1 &

    echo $! > "$LOG_DIR/vllm_group_${name,,}.pid"
    log "  组 $name PID: $(cat $LOG_DIR/vllm_group_${name,,}.pid)"
}

stop_group() {
    local name=$1
    local pid_file="$LOG_DIR/vllm_group_${name,,}.pid"

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 $PID 2>/dev/null; then
            log "停止组 $name (PID: $PID)..."
            kill $PID
        fi
        rm -f "$pid_file"
    fi
}

start_all() {
    log "启动 3 组 vLLM 服务 (TP=2 × 3)..."

    for i in 0 1 2; do
        start_group $i "${GPU_GROUPS[$i]}" "${PORTS[$i]}" "${NAMES[$i]}"
    done

    # 等待所有服务就绪
    log "等待所有服务启动..."
    for port in "${PORTS[@]}"; do
        for j in {1..60}; do
            if curl -s "http://localhost:$port/v1/models" > /dev/null 2>&1; then
                log "  端口 $port 就绪"
                break
            fi
            sleep 5
            log "  等待端口 $port... ($j/60)"
        done
    done

    log "所有服务启动完成"
}

stop_all() {
    log "停止所有 vLLM 服务..."
    for name in "${NAMES[@]}"; do
        stop_group "$name"
    done
    log "所有服务已停止"
}

status() {
    log "vLLM 服务状态:"
    echo ""

    for i in 0 1 2; do
        local name="${NAMES[$i]}"
        local port="${PORTS[$i]}"
        local pid_file="$LOG_DIR/vllm_group_${name,,}.pid"

        echo "组 $name (端口 $port):"

        if [ -f "$pid_file" ]; then
            PID=$(cat "$pid_file")
            if kill -0 $PID 2>/dev/null; then
                echo "  状态: 运行中 (PID: $PID)"
                if curl -s "http://localhost:$port/v1/models" > /dev/null 2>&1; then
                    MODEL_NAME=$(curl -s "http://localhost:$port/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "未知")
                    echo "  模型: $MODEL_NAME"
                else
                    echo "  模型: 加载中..."
                fi
            else
                echo "  状态: 未运行 (PID 文件存在但进程已退出)"
            fi
        else
            echo "  状态: 未启动"
        fi
        echo ""
    done
}

# =============================================================================
# 主逻辑
# =============================================================================

main() {
    check_vllm

    case "${1:-start}" in
        start)
            check_cuda
            stop_all
            start_all
            ;;
        stop)
            stop_all
            ;;
        status)
            status
            ;;
        *)
            echo "使用方法: $0 [start|stop|status]"
            echo ""
            echo "  start  - 启动 3 组服务 (默认)"
            echo "  stop   - 停止所有服务"
            echo "  status - 查看服务状态"
            exit 1
            ;;
    esac
}

main "$@"