#!/bin/bash
# 服务器安全加固脚本
# 在阿里云ECS上执行此脚本以防止再次被入侵

set -e

echo "=== 🔒 开始安全加固 ==="

# 1. 禁用密码登录，仅允许SSH密钥
echo "📝 步骤1：禁用SSH密码登录..."
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#PasswordAuthentication no/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
grep -q "^PasswordAuthentication" /etc/ssh/sshd_config || echo "PasswordAuthentication no" >> /etc/ssh/sshd_config

# 2. 限制root用户仅能通过密钥登录
echo "📝 步骤2：配置root用���SSH策略..."
sed -i 's/^PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#PermitRootLogin yes/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
grep -q "^PermitRootLogin" /etc/ssh/sshd_config || echo "PermitRootLogin prohibit-password" >> /etc/ssh/sshd_config

# 3. 更改SSH默认端口（从22改为22222）
echo "📝 步骤3：更改SSH端口为22222..."
sed -i 's/^#Port 22/Port 22222/' /etc/ssh/sshd_config
sed -i 's/^Port 22/Port 22222/' /etc/ssh/sshd_config
grep -q "^Port" /etc/ssh/sshd_config || echo "Port 22222" >> /etc/ssh/sshd_config

# 4. 配置防火墙规则
echo "📝 步骤4：配置iptables防火墙..."
iptables -F
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport 22222 -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 8787 -j ACCEPT
iptables -A INPUT -j DROP
service iptables save || iptables-save > /etc/sysconfig/iptables

# 5. 安装fail2ban防止暴力破解
echo "📝 步骤5：安装fail2ban..."
if ! command -v fail2ban-server &> /dev/null; then
    yum install -y epel-release
    yum install -y fail2ban
    cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = 22222
logpath = /var/log/secure
EOF
    systemctl enable fail2ban
    systemctl start fail2ban
fi

# 6. 重启SSH服务
echo "📝 步骤6：重启SSH服务..."
systemctl restart sshd

echo ""
echo "✅ 安全加固完成！"
echo ""
echo "🔑 重要提醒："
echo "1. SSH端口已改为 22222（请在阿里云安全组开放此端口）"
echo "2. 密码登录已禁用（请确保SSH密钥已配置）"
echo "3. 防火墙规则已配置"
echo "4. fail2ban已启用（3次失败登录封禁1小时）"
echo ""
echo "⚠️ 下次登录命令："
echo "   ssh -p 22222 root@139.196.232.136"
echo ""
