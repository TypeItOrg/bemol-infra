
<!-- Banner -->
<p align="center">
<img width="2172" height="724" alt="bemol_banner_logo_pua_original" src="https://github.com/user-attachments/assets/2523e8dd-3399-4b8b-bae3-5dd62ba7b039" />

</p>

<!-- Tecnologías: Infraestructura & Servicios -->
<p align="center">
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker Compose" /></a>
  <a href="https://nginx.org/"><img src="https://img.shields.io/badge/Nginx-Reverse_Proxy-009639?style=for-the-badge&logo=nginx&logoColor=white" alt="Nginx" /></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-18-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL 18" /></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-7-FF4438?style=for-the-badge&logo=redis&logoColor=white" alt="Redis 7" /></a>
</p>

<!-- Tecnologías: Automation & DevOps -->
<p align="center">
  <a href="https://github.com/features/actions"><img src="https://img.shields.io/badge/CD-GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions CD" /></a>
  <a href="https://ghcr.io"><img src="https://img.shields.io/badge/Registry-GHCR-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub Container Registry" /></a>
  <a href="https://pubs.opengroup.org/onlinepubs/9799919799/"><img src="https://img.shields.io/badge/Shell-POSIX-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white" alt="POSIX Shell" /></a>
  <a href="https://www.linux.org/"><img src="https://img.shields.io/badge/Runtime-Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" alt="Linux" /></a>
</p>

<!-- Presentación -->
<h1 align="center">Bemol</h1>
<p align="center">
  Bemol es una plataforma que centraliza inscripciones, cursadas, calificaciones y procesos administrativos <strong>en un solo lugar</strong>.
  Pensada para <strong>estudiantes, docentes y personal administrativo</strong>, ofrece un espacio donde gestionar actividades,
  consultar información académica y dar seguimiento a los distintos procesos institucionales,
  mejorando la organización y facilitando la gestión cotidiana.
</p>

## Ramas y entornos

- `staging` es la rama principal y versiona la configuración instalada en el VPS.
- Producción no está configurada; `main` se creará cuando se prepare ese entorno.
- Para operar el VPS, usa un checkout de la rama `staging`.

## Operación de staging

- [Despliegues por SSH, variables y datos](docs/STAGING.md).
- [Reglas públicas de Traefik](deploy/traefik/traefik-staging.yaml) y [configuración estática de referencia](deploy/traefik/traefik-static.staging.example.yaml).
- [Compose base de la aplicación](compose.yaml) y [diferencias de staging](compose.staging.yaml).
- [Compose del proxy Traefik independiente](compose.proxy.yaml).

`make deploy-staging` valida el entorno privado, descarga las imágenes de aplicación,
crea y valida un backup de PostgreSQL y actualiza los contenedores. Los cinco
volúmenes de datos existentes son externos y no se crean implícitamente.
Traefik usa archivos privados de `/etc/bemol/traefik`, sin socket de Docker;
su dashboard requiere autenticación propia.
