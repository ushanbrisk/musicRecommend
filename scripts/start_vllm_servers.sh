#!/bin/bash
# =============================================================================
# vLLM 模型服务启动脚本
# =============================================================================
# 根据 inference.md 设计，启动两组 vLLM 服务：
#   - 组 A: 2 × RTX 3090 (24GB) → Qwen3.6-27B (Int4, TP=2), 端口 8000
#   - 组 B: 4 × RTX 3080 (20GB) → Qwen3.6-30B-A3B (MoE, Int4, TP=4), 端口 8001
#
# 使用方法:
#   bash scripts/start_vllm_servers.sh [group_a|group_b|all]
#
# 注意: 需要先安装 vLLM: pip install vllm>=0.4.0
# =============================================================================

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# vLLM 模型配置（根据 inference.md）
# 实际硬件配置：GPU 0,4,5 是 3090(24GB)，GPU 1,2,3 是 3080(20GB)

# 组 A: 2 × RTX 3090 (GPU 0, 4)
MODEL_GROUP_A="Qwen/Qwen2.5-32B-Instruct-AWQ"
TP_GROUP_A=2
PORT_GROUP_A=8000
GPU_GROUP_A="0,4"

# 组 B: 2 × RTX 3080 (GPU 1, 2)
MODEL_GROUP_B="Qwen/Qwen2.5-14B-Instruct-AWQ"
TP_GROUP_B=2
PORT_GROUP_B=8001
GPU_GROUP_B="1,2"

# 通用配置
QUANTIZATION="awq"
MAX_MODEL_LEN=8192
MAX_NUM_SEQS_GROUP_A=32
MAX_NUM_SEQS_GROUP_B=64
GPU_MEMORY_UTILIZATION=0.90

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
        error "vLLM 未安装，请运行: pip install vllm>=0.4.0"
        exit 1
    fi
}

check_cuda() {
    if ! command -v nvidia-smi &> /dev/null; then
        error "nvidia-smi 未找到，CUDA 可能未正确安装"
        exit 1
    fi

    log "检测到的 GPU:"
    nvidia-smi --query-gpu=index,name,memory.total --format=csv
}

# =============================================================================
# 启动函数
# =============================================================================

start_group_a() {
    log "启动组 A 服务..."
    log "  模型: $MODEL_GROUP_A"
    log "  量化: $QUANTIZATION"
    log "  张量并行: $TP_GROUP_A"
    log "  端口: $PORT_GROUP_A"
    log "  GPU: $GPU_GROUP_A (2×RTX 3090)"

    export CUDA_VISIBLE_DEVICES="$GPU_GROUP_A"

    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL_GROUP_A" \
        --quantization "$QUANTIZATION" \
        --tensor-parallel-size $TP_GROUP_A \
        --host 0.0.0.0 \
        --port $PORT_GROUP_A \
        --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
        --max-model-len $MAX_MODEL_LEN \
        --max-num-seqs $MAX_NUM_SEQS_GROUP_A \
        --trust-remote-code \
        > "$LOG_DIR/vllm_group_a.log" 2>&1 &

    echo $! > "$LOG_DIR/vllm_group_a.pid"
    log "组 A 服务已启动，PID: $(cat $LOG_DIR/vllm_group_a.pid)"
    log "日志: $LOG_DIR/vllm_group_a.log"
}

start_group_b() {
    log "启动组 B 服务..."
    log "  模型: $MODEL_GROUP_B"
    log "  量化: $QUANTIZATION"
    log "  张量并行: $TP_GROUP_B"
    log "  端口: $PORT_GROUP_B"
    log "  GPU: $GPU_GROUP_B (2×RTX 3080)"

    export CUDA_VISIBLE_DEVICES="$GPU_GROUP_B"

    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL_GROUP_B" \
        --quantization "$QUANTIZATION" \
        --tensor-parallel-size $TP_GROUP_B \
        --host 0.0.0.0 \
        --port $PORT_GROUP_B \
        --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
        --max-model-len $MAX_MODEL_LEN \
        --max-num-seqs $MAX_NUM_SEQS_GROUP_B \
        --trust-remote-code \
        > "$LOG_DIR/vllm_group_b.log" 2>&1 &

    echo $! > "$LOG_DIR/vllm_group_b.pid"
    log "组 B 服务已启动，PID: $(cat $LOG_DIR/vllm_group_b.pid)"
    log "日志: $LOG_DIR/vllm_group_b.log"
}

stop_group_a() {
    if [ -f "$LOG_DIR/vllm_group_a.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_group_a.pid")
        if kill -0 $PID 2>/dev/null; then
            log "停止组 A 服务 (PID: $PID)..."
            kill $PID
            rm -f "$LOG_DIR/vllm_group_a.pid"
        fi
    fi
}

stop_group_b() {
    if [ -f "$LOG_DIR/vllm_group_b.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_group_b.pid")
        if kill -0 $PID 2>/dev/null; then
            log "停止组 B 服务 (PID: $PID)..."
            kill $PID
            rm -f "$LOG_DIR/vllm_group_b.pid"
        fi
    fi
}

status() {
    log "vLLM 服务状态:"
    echo ""

    if [ -f "$LOG_DIR/vllm_group_a.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_group_a.pid")
        if kill -0 $PID 2>/dev/null; then
            echo "  组 A: 运行中 (PID: $PID)"
            curl -s "http://localhost:$PORT_GROUP_A/v1/models" > /dev/null 2>&1 && echo "    模型加载完成" || echo "    模型加载中..."
        else
            echo "  组 A: 未运行"
        fi
    else
        echo "  组 A: 未启动"
    fi

    if [ -f "$LOG_DIR/vllm_group_b.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_group_b.pid")
        if kill -0 $PID 2>/dev/null; then
            echo "  组 B: 运行中 (PID: $PID)"
            curl -s "http://localhost:$PORT_GROUP_B/v1/models" > /dev/null 2>&1 && echo "    模型加载完成" || echo "    模型加载中..."
        else
            echo "  组 B: 未运行"
        fi
    else
        echo "  组 B: 未启动"
    fi
}

wait_for_ready() {
    local port=$1
    local name=$2
    log "等待 $name 服务就绪..."

    for i in {1..60}; do
        if curl -s "http://localhost:$port/v1/models" > /dev/null 2>&1; then
            log "$name 服务已就绪"
            return 0
        fi
        sleep 5
        log "  等待中... ($i/60)"
    done

    error "$name 服务启动超时"
    return 1
}

# =============================================================================
# 主逻辑
# =============================================================================

main() {
    check_vllm
    check_cuda

    case "${1:-all}" in
        group_a)
            stop_group_a
            start_group_a
            wait_for_ready $PORT_GROUP_A "组 A"
            ;;
        group_b)
            stop_group_b
            start_group_b
            wait_for_ready $PORT_GROUP_B "组 B"
            ;;
        all)
            stop_group_a
            stop_group_b
            start_group_a
            start_group_b
            wait_for_ready $PORT_GROUP_A "组 A" &
            wait_for_ready $PORT_GROUP_B "组 B" &
            wait
            ;;
        stop)
            stop_group_a
            stop_group_b
            log "所有 vLLM 服务已停止"
            ;;
        status)
            status
            ;;
        *)
            echo "使用方法: $0 [group_a|group_b|all|stop|status]"
            echo ""
            echo "  group_a  - 启动组 A (3×RTX 3090: GPU 0,4,5 → Qwen2.5-32B-Instruct)"
            echo "  group_b  - 启动组 B (3×RTX 3080: GPU 1,2,3 → Qwen2.5-14B-Instruct)"
            echo "  all      - 启动所有服务 (默认)"
            echo "  stop     - 停止所有服务"
            echo "  status   - 查看服务状态"
            exit 1
            ;;
    esac
}

main "$@"
