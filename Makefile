# AutoTrade 项目 Makefile

.PHONY: backend frontend dev install-backend install-frontend check help

# 默认目标
.DEFAULT_GOAL := help

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# 安装后端依赖
install-backend: ## 安装 Python 依赖
	cd backend && pip install -r requirements.txt

# 安装前端依赖
install-frontend: ## 安装 Node.js 依赖
	cd frontend && npm install

# 安装所有依赖
install: install-backend install-frontend ## 安装所有依赖

# 启动后端（开发模式）
backend: ## 启动后端服务 (http://localhost:18000)
	@echo "🚀 Starting backend on http://localhost:18000"
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 18000

# 启动前端
frontend: ## 启动前端服务 (http://localhost:13000)
	@echo "🎨 Starting frontend on http://localhost:13000"
	cd frontend && npm run dev

# 同时启动前后端
dev: ## 一键启动前后端服务
	@python start.py

# 快速启动别名
start: dev ## 一键启动所有服务（同 make dev）

# 检查项目结构
check: ## 检查项目结构完整性
	@echo "📁 Backend structure:"
	@ls -la backend/app/
	@echo ""
	@echo "📁 Frontend structure:"
	@ls -la frontend/src/app/

# 运行测试
test: ## 运行测试
	cd backend && pytest

# 代码格式化
format: ## 格式化代码
	cd backend && black app/ 2>/dev/null || echo "black not installed"
	cd frontend && npm run lint -- --fix 2>/dev/null || echo "lint completed"

# 清理临时文件
clean: ## 清理临时文件
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned up temporary files"

# 数据库重置
db-reset: ## 重置数据库
	@rm -f backend/autotrade.db
	@echo "✅ Database reset. Restart backend to reinitialize."

# 项目初始化
init: ## 初始化项目结构
	@python ~/.agents/skills/autotrade-dev/scripts/init_project.py
