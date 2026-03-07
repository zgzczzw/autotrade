#!/usr/bin/env python3
"""
AutoTrade 一键启动脚本
同时启动后端和前端服务

默认端口：
    - 后端: 18000
    - 前端: 13000

Usage:
    python3 start.py
    python3 start.py --no-backend      # 只启动前端
    python3 start.py --no-frontend     # 只启动后端
    python3 start.py --no-auto-kill    # 不自动结束占用端口的进程
    python3 start.py --clean           # 仅清理残留进程
    python3 start.py --backend-port 8001 --frontend-port 3001  # 自定义端口

日志位置：
    - 控制台输出：实时显示
    - 启动日志：logs/launcher.log

故障排查：
    如果启动失败，脚本会自动清理残留进程
    或手动执行: python3 start.py --clean
"""

import argparse
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 配置日志目录
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            LOG_DIR / "launcher.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("launcher")


# 颜色配置
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_banner():
    """打印启动横幅"""
    banner = rf"""{Colors.CYAN}{Colors.BOLD}
    ___       __        __            ______
   /   | ____/ /_____ _/ /___  ____  /_  __/__  ____  __________
  / /| |/ __  / __/ __  / __ \/ __ \  / / / _ \/ __ \/ ___/ ___/
 / ___ / /_/ / /  / /_/ / /_/ / /_/ / / / /  __/ / / / /__(__  )
/_/  |_\__,_/_/   \__,_/\____/ .___/ /_/  \___/_/ /_/\___/____/
                            /_/
{Colors.ENDC}
{Colors.GREEN}                    加密货币自动交易平台{Colors.ENDC}
"""
    print(banner)
    logger.info("=" * 60)
    logger.info("启动脚本初始化")
    logger.info(f"日志文件: {LOG_DIR / 'launcher.log'}")


def log_backend(msg):
    """打印后端日志"""
    print(f"{Colors.BLUE}[后端]{Colors.ENDC} {msg}")
    logger.info(f"[后端] {msg}")


def log_frontend(msg):
    """打印前端日志"""
    print(f"{Colors.YELLOW}[前端]{Colors.ENDC} {msg}")
    logger.info(f"[前端] {msg}")


def log_info(msg):
    """打印信息日志"""
    print(f"{Colors.CYAN}[信息]{Colors.ENDC} {msg}")
    logger.info(f"[信息] {msg}")


def log_error(msg):
    """打印错误日志"""
    print(f"{Colors.RED}[错误]{Colors.ENDC} {msg}", file=sys.stderr)
    logger.error(f"[错误] {msg}")


def check_backend_env():
    """检查后端环境"""
    backend_dir = Path(__file__).parent / "backend"
    venv_python = backend_dir / "venv" / "bin" / "python"
    
    if not venv_python.exists():
        log_error("后端虚拟环境不存在，请先运行: cd backend && python3 -m venv venv")
        return False
    
    return True


def check_frontend_env():
    """检查前端环境"""
    frontend_dir = Path(__file__).parent / "frontend"
    node_modules = frontend_dir / "node_modules"
    
    if not node_modules.exists():
        log_error("前端依赖未安装，请先运行: cd frontend && npm install")
        return False
    
    return True


def is_port_in_use(port, host="127.0.0.1"):
    """检查端口是否真正被进程占用（用 connect 而非 bind，避免 TIME_WAIT 误判）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect((host, port))
            return True  # 连接成功，有进程在监听
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False  # 连接被拒绝，端口空闲


def get_process_using_port(port):
    """获取占用指定端口的进程 PID"""
    try:
        # 使用 lsof 或 netstat 查找占用端口的进程
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            pids = [int(pid.strip()) for pid in result.stdout.strip().split('\n') if pid.strip()]
            return pids
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    
    # 备用方案：使用 ps 和 grep
    try:
        result = subprocess.run(
            ["sh", "-c", f"ps aux | grep -E '({port}|uvicorn|next)' | grep -v grep"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            pids = []
            for line in lines:
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pids.append(int(parts[1]))
                    except ValueError:
                        continue
            return pids
    except (subprocess.TimeoutExpired, ValueError):
        pass
    
    return []


def kill_processes(pids, port, service_name):
    """结束进程"""
    killed = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
            logger.info(f"发送终止信号到 {service_name} 进程 (PID: {pid}, 端口: {port})")
        except ProcessLookupError:
            pass  # 进程已经不存在
        except PermissionError:
            log_error(f"无权限结束进程 {pid}，尝试使用 sudo")
            return False
    
    # 等待进程结束
    if killed:
        log_info(f"等待 {service_name} 进程结束...")
        time.sleep(2)
        
        # 检查是否还在运行
        for pid in killed:
            try:
                os.kill(pid, 0)  # 检查进程是否存在
                # 进程还在，强制终止
                os.kill(pid, signal.SIGKILL)
                logger.info(f"强制终止 {service_name} 进程 (PID: {pid})")
            except ProcessLookupError:
                pass  # 进程已经结束
        
        # 再次等待
        time.sleep(1)
        
        # 检查端口是否释放
        if is_port_in_use(port):
            log_error(f"端口 {port} 仍被占用，请手动检查")
            return False
        else:
            log_info(f"端口 {port} 已释放")
            return True
    
    return True


def force_cleanup_ports(ports):
    """
    强制清理占用指定端口的所有进程
    
    Args:
        ports: 端口号列表
    """
    log_info("正在强制清理残留进程...")
    
    for port in ports:
        # 方法1: 使用 lsof 查找并终止
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        try:
                            os.kill(int(pid.strip()), signal.SIGKILL)
                            logger.info(f"已终止进程 {pid} (占用端口 {port})")
                        except:
                            pass
        except:
            pass
    
    # 方法2: 批量终止所有 uvicorn 和 next 进程
    try:
        subprocess.run(
            "ps aux | grep -E 'uvicorn|next' | grep -v grep | awk '{print $2}' | xargs -r kill -9 2>/dev/null",
            shell=True,
            timeout=3
        )
        logger.info("已清理所有 uvicorn 和 next 进程")
    except:
        pass
    
    # 等待端口释放
    time.sleep(1)
    
    # 验证清理结果（只要 lsof 找不到占用进程，视为端口可用）
    for port in ports:
        pids = []
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = [p for p in result.stdout.strip().split('\n') if p.strip()]
        except Exception:
            pass
        if pids:
            log_error(f"端口 {port} 仍有进程占用: {pids}，可能需要手动清理")
        else:
            log_info(f"端口 {port} 已释放")


def check_and_free_ports(backend_port, frontend_port, no_backend=False, no_frontend=False, auto_kill=True):
    """
    检查端口并尝试释放被占用的端口
    
    Args:
        auto_kill: 是否自动结束占用端口的进程
    
    Returns:
        bool: 端口是否可用
    """
    ports_to_check = []
    
    if not no_backend:
        ports_to_check.append(("backend", backend_port, "0.0.0.0"))
    
    if not no_frontend:
        ports_to_check.append(("frontend", frontend_port, "127.0.0.1"))
    
    # 先进行强制清理
    force_cleanup_ports([p[1] for p in ports_to_check])
    
    for service_name, port, host in ports_to_check:
        if is_port_in_use(port):
            log_info(f"{service_name} 端口 {port} 被占用")
            
            if not auto_kill:
                log_error(f"端口 {port} 已被占用，请使用 --{service_name}-port 指定其他端口")
                return False
            
            # 获取占用端口的进程
            pids = get_process_using_port(port)
            
            if not pids:
                log_error(f"无法获取占用端口 {port} 的进程信息")
                log_info(f"尝试使用其他端口: python3 start.py --{service_name}-port {port + 1}")
                return False
            
            log_info(f"发现占用端口 {port} 的进程: {pids}")
            
            # 尝试结束进程
            if not kill_processes(pids, port, service_name):
                return False
    
    return True


class ProcessManager:
    """进程管理器"""
    
    def __init__(self):
        self.processes = []
        self.running = True
        self.output_threads = []
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """信号处理"""
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        log_info(f"\n收到 {sig_name} 信号，正在停止所有服务...")
        logger.info(f"收到信号 {sig_name}，开始停止服务")
        self.stop_all()
        logger.info("服务已停止，退出程序")
        sys.exit(0)
    
    def start_backend(self, port=8000, host="0.0.0.0"):
        """启动后端服务"""
        backend_dir = Path(__file__).parent / "backend"
        venv_python = backend_dir / "venv" / "bin" / "python"
        
        # 使用 -u 参数强制无缓冲输出
        cmd = [
            str(venv_python), "-u",
            "-m", "uvicorn",
            "app.main:app",
            "--reload",
            "--host", host,
            "--port", str(port),
        ]
        
        log_info(f"启动后端服务: http://{host}:{port}")
        
        process = subprocess.Popen(
            cmd,
            cwd=backend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        
        self.processes.append(("backend", process))
        
        # 启动输出线程
        thread = threading.Thread(target=self.stream_output, args=("backend", process), daemon=True)
        thread.start()
        self.output_threads.append(thread)
        
        return process
    
    def start_frontend(self, port=3000):
        """启动前端服务"""
        frontend_dir = Path(__file__).parent / "frontend"
        
        cmd = ["npm", "run", "dev"]
        
        log_info(f"启动前端服务: http://localhost:{port}")
        
        # 设置环境变量
        env = os.environ.copy()
        env["PORT"] = str(port)
        
        process = subprocess.Popen(
            cmd,
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
        
        self.processes.append(("frontend", process))
        
        # 启动输出线程
        thread = threading.Thread(target=self.stream_output, args=("frontend", process), daemon=True)
        thread.start()
        self.output_threads.append(thread)
        
        return process
    
    def stream_output(self, name, process):
        """流式输出进程日志"""
        try:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break
                line = line.rstrip()
                if name == "backend":
                    log_backend(line)
                else:
                    log_frontend(line)
        except Exception as e:
            if self.running:  # 只有在正常运行时才报错
                log_error(f"读取 {name} 输出时出错: {e}")
        finally:
            if process.stdout:
                process.stdout.close()
    
    def monitor_processes(self):
        """监控进程状态"""
        startup_time = time.time()
        min_startup_time = 3  # 最小启动时间（秒）
        
        while self.running and self.processes:
            for i in range(len(self.processes) - 1, -1, -1):
                name, process = self.processes[i]
                retcode = process.poll()
                if retcode is not None:
                    # 如果进程在启动时间内退出，可能是启动失败
                    if time.time() - startup_time < min_startup_time:
                        log_error(f"{name} 进程启动失败 (code: {retcode})")
                        if name == "backend":
                            log_error(f"可能原因: 端口被占用、虚拟环境问题或代码错误")
                            log_info(f"尝试手动运行: cd backend && source venv/bin/activate && python -m uvicorn app.main:app --reload")
                        elif name == "frontend":
                            log_error(f"可能原因: 端口被占用、依赖缺失或代码错误")
                            log_info(f"尝试手动运行: cd frontend && npm run dev")
                    else:
                        log_error(f"{name} 进程已退出 (code: {retcode})")
                    
                    del self.processes[i]
                    
                    # 如果一个进程退出，停止另一个
                    if self.running:
                        log_info("一个服务已停止，正在停止其他服务...")
                        self.stop_all()
                        return
            
            time.sleep(0.1)
    
    def stop_all(self):
        """停止所有进程"""
        self.running = False
        logger.info("开始停止所有服务...")
        
        for name, process in self.processes:
            if process.poll() is None:  # 进程仍在运行
                log_info(f"正在停止 {name}...")
                logger.info(f"发送终止信号到 {name} 进程 (PID: {process.pid})")
                process.terminate()
                
                # 等待进程结束（最多 5 秒）
                try:
                    process.wait(timeout=5)
                    logger.info(f"{name} 进程已正常退出")
                except subprocess.TimeoutExpired:
                    log_error(f"{name} 未响应，强制终止")
                    logger.error(f"{name} 进程未响应，强制终止 (PID: {process.pid})")
                    process.kill()
                    process.wait()
        
        self.processes.clear()
        log_info("所有服务已停止")
        logger.info("所有服务已停止")


def main():
    parser = argparse.ArgumentParser(description="AutoTrade 一键启动脚本")
    parser.add_argument(
        "--no-backend",
        action="store_true",
        help="只启动前端，不启动后端",
    )
    parser.add_argument(
        "--no-frontend",
        action="store_true",
        help="只启动后端，不启动前端",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=18000,
        help="后端服务端口 (默认: 18000)",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=13000,
        help="前端服务端口 (默认: 13000)",
    )
    parser.add_argument(
        "--no-auto-kill",
        action="store_true",
        help="不自动结束占用端口的进程",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="仅清理残留进程后退出",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="后端服务监听地址 (默认: 0.0.0.0)",
    )
    
    args = parser.parse_args()
    
    # 如果只清理进程，执行后退出
    if args.clean:
        print_banner()
        log_info("执行清理模式...")
        force_cleanup_ports([args.backend_port, args.frontend_port])
        log_info("清理完成")
        sys.exit(0)
    
    # 打印横幅
    print_banner()
    
    logger.info(f"启动参数: backend={not args.no_backend}, frontend={not args.no_frontend}, "
                f"backend_port={args.backend_port}, frontend_port={args.frontend_port}")
    
    # 检查环境
    if not args.no_backend and not check_backend_env():
        logger.error("后端环境检查失败")
        sys.exit(1)
    
    if not args.no_frontend and not check_frontend_env():
        logger.error("前端环境检查失败")
        sys.exit(1)
    
    # 检查并释放端口（会自动清理残留进程）
    auto_kill = not args.no_auto_kill
    if not check_and_free_ports(args.backend_port, args.frontend_port, args.no_backend, args.no_frontend, auto_kill):
        logger.error("端口检查失败")
        sys.exit(1)
    
    # 创建进程管理器
    manager = ProcessManager()
    
    # 启动服务
    try:
        if not args.no_backend:
            manager.start_backend(port=args.backend_port, host=args.host)
            time.sleep(1)  # 等待后端启动
        
        if not args.no_frontend:
            manager.start_frontend(port=args.frontend_port)
            time.sleep(1)  # 等待前端启动
        
        # 打印访问信息
        print()
        log_info(f"{Colors.GREEN}{Colors.BOLD}服务已启动！{Colors.ENDC}")
        if not args.no_backend:
            log_info(f"后端 API:   http://localhost:{args.backend_port}")
            log_info(f"API 文档:   http://localhost:{args.backend_port}/docs")
        if not args.no_frontend:
            log_info(f"前端页面:   http://localhost:{args.frontend_port}")
        print()
        log_info("按 Ctrl+C 停止所有服务")
        print()
        
        # 监控进程
        try:
            manager.monitor_processes()
        except KeyboardInterrupt:
            logger.info("收到键盘中断，正常退出")
            pass  # 正常退出
        
    except Exception as e:
        log_error(f"启动失败: {e}")
        manager.stop_all()
        sys.exit(1)


if __name__ == "__main__":
    main()
