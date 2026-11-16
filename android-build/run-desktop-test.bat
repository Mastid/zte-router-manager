@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  中兴路由管家 - App 协议真机测试
echo  会执行：登录 - 读取 - 读WiFi密码 - 原值回填保存
echo  （保存会短暂重启无线，约 10 秒；不重启路由器）
echo ============================================
echo.
jdk-17.0.2\bin\java.exe -Dfile.encoding=UTF-8 -cp out\classes ZteTest live
echo.
echo 结果已保存到 test-result.txt
pause
