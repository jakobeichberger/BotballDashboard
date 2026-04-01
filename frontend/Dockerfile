FROM nginx:alpine
# dist/ is pre-built on the Proxmox host by scripts/proxmox-setup.sh.
# Building inside Docker fails on Proxmox VE because the AppArmor docker
# profile blocks socketpair(), which esbuild (used by vite/workbox) requires
# to spawn its child process.  The host build runs fine since AppArmor does
# not apply there.
COPY dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
