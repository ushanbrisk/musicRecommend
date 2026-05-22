#!/bin/bash
# =============================================================================
# vLLM 模型服务启动脚本 v2
# =============================================================================
# 使用单一大模型 + Tensor Parallel = 5
# 硬件配置：3 × RTX 3090 (24GB) + 2 × RTX 3080 (20GB) = 5 张卡
#
# 优势：
#   - 只需加载一个大模型权重，节省显存
#   - TP=5 将权重分片到 5 张卡，每张卡负担更小
#   - head_num=40，TP=5 时每卡 8 个 head
#
# 使用方法:
#   bash scripts/start_vllm_servers_v2.sh [start|stop|status]
#
# 注意: 需要先安装 vLLM: pip install vllm>=0.4.0
# =============================================================================

set -e

# 确保 GPU 顺序一致（按 PCI 总线 ID 排序）
export CUDA_DEVICE_ORDER=PCI_BUS_ID

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

# vLLM 模型配置
# GPU 分配：2 × 3090 (GPU 0,4) + 2 × 3080 (GPU 1,2) = 4 张卡
# 注意：词表大小 152064 必须能被 TP 整除，因此使用 TP=4
MODEL="Qwen/Qwen2.5-32B-Instruct-AWQ"
TP=4
PORT=8000
GPU_IDS="0,1,2,4"

# 通用配置
QUANTIZATION="awq"
MAX_MODEL_LEN=8192
MAX_NUM_SEQS=64
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
    echo ""
    log "将使用的 GPU: $GPU_IDS (2×3090 + 2×3080, TP=$TP)"
}

# =============================================================================
# 服务控制函数
# =============================================================================

start() {
    log "启动 vLLM 服务..."
    log "  模型: $MODEL"
    log "  量化: $QUANTIZATION"
    log "  张量并行: $TP"
    log "  端口: $PORT"
    log "  GPU: $GPU_IDS (2×RTX 3090 + 2×RTX 3080)"

    export CUDA_VISIBLE_DEVICES="$GPU_IDS"

    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL" \
        --quantization "$QUANTIZATION" \
        --tensor-parallel-size $TP \
        --host 0.0.0.0 \
        --port $PORT \
        --gpu-memory-utilization $GPU_MEMORY_UTILIZATION \
        --max-model-len $MAX_MODEL_LEN \
        --max-num-seqs $MAX_NUM_SEQS \
        --trust-remote-code \
        > "$LOG_DIR/vllm_single.log" 2>&1 &

    echo $! > "$LOG_DIR/vllm_single.pid"
    log "服务已启动，PID: $(cat $LOG_DIR/vllm_single.pid)"
    log "日志: $LOG_DIR/vllm_single.log"
}

stop() {
    if [ -f "$LOG_DIR/vllm_single.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_single.pid")
        if kill -0 $PID 2>/dev/null; then
            log "停止 vLLM 服务 (PID: $PID)..."
            kill $PID
            rm -f "$LOG_DIR/vllm_single.pid"
        else
            log "服务未运行"
            rm -f "$LOG_DIR/vllm_single.pid"
        fi
    else
        log "服务未运行"
    fi
}

status() {
    log "vLLM 服务状态:"
    echo ""

    if [ -f "$LOG_DIR/vllm_single.pid" ]; then
        PID=$(cat "$LOG_DIR/vllm_single.pid")
        if kill -0 $PID 2>/dev/null; then
            echo "  状态: 运行中 (PID: $PID)"
            if curl -s "http://localhost:$PORT/v1/models" > /dev/null 2>&1; then
                echo "  模型: 已加载"
                MODEL_NAME=$(curl -s "http://localhost:$PORT/v1/models" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "未知")
                echo "  模型名称: $MODEL_NAME"
            else
                echo "  模型: 加载中..."
            fi
        else
            echo "  状态: 未运行 (PID 文件存在但进程已退出)"
        fi
    else
        echo "  状态: 未启动"
    fi
}

wait_for_ready() {
    log "等待服务就绪..."

    for i in {1..120}; do
        if curl -s "http://localhost:$PORT/v1/models" > /dev/null 2>&1; then
            log "服务已就绪"
            return 0
        fi
        sleep 5
        log "  等待中... ($i/120)"
    done

    error "服务启动超时"
    return 1
}

# =============================================================================
# 主逻辑
# =============================================================================

main() {
    check_vllm
    check_cuda

    case "${1:-start}" in
        start)
            stop
            start
            wait_for_ready
            ;;
        stop)
            stop
            ;;
        status)
            status
            ;;
        *)
            echo "使用方法: $0 [start|stop|status]"
            echo ""
            echo "  start  - 启动服务 (默认)"
            echo "  stop   - 停止服务"
            echo "  status - 查看服务状态"
            exit 1
            ;;
    esac
}

main "$@"