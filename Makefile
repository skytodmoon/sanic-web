# 导入子模块的 Makefile
include web/Makefile

# 构建 Vue 3 前端项目镜像
web-build:
	$(MAKE) -C web docker-build

# 构建服务端镜像
service-build:
	docker build -t $(DOCKER_IMAGE) -f ./docker/Dockerfile .


.PHONY: web-build service-build