# Server Setup Runbook — SCTUBUNTU01 (One-time, Manual)

ทำครั้งเดียวก่อน Deploy App แรกที่ต้องผ่าน Nginx Proxy Manager (NPM)
ต้องทำเองผ่าน SSH หรือ Portainer UI — Session นี้ไม่มีเครื่องมือเข้าถึง
Server 10.206.1.107 โดยตรง

อ้างอิงแนวทางเต็มที่ [`00_KICKOFF_AND_DESIGN.md`](00_KICKOFF_AND_DESIGN.md) ข้อ 3.3

---

## ขั้นตอนที่ 1 — SSH เข้าเครื่อง

```bash
ssh <your-user>@10.206.1.107
```

## ขั้นตอนที่ 2 — สร้าง Network กลาง `npm_proxy`

```bash
docker network create npm_proxy
```

ถ้าเจอ error ว่ามีอยู่แล้ว (`already exists`) ข้ามไปขั้นตอนถัดไปได้เลย ไม่ต้องแก้อะไร

## ขั้นตอนที่ 3 — หาชื่อ Container ของ Nginx Proxy Manager

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" | grep -i nginx
```

จดค่าคอลัมน์ `NAMES` ไว้ (เช่น `nginx-proxy-manager-app-1` — ชื่อจริงขึ้นกับตอน Deploy
Stack ครั้งแรก)

## ขั้นตอนที่ 4 — ต่อ Container NPM เข้ากับ Network ใหม่ (ทันที ไม่มี Downtime)

```bash
docker network connect npm_proxy <ชื่อ-container-จากขั้นตอนที่-3>
```

## ขั้นตอนที่ 5 — ตรวจสอบว่าติดแล้วจริง

```bash
docker network inspect npm_proxy --format '{{range .Containers}}{{.Name}} {{end}}'
```

ต้องเห็นชื่อ Container ของ NPM อยู่ในผลลัพธ์

## ขั้นตอนที่ 6 (สำคัญ — กันหลุดตอน Redeploy ในอนาคต)

ขั้นตอนที่ 4 เป็นการต่อ Network แบบ Manual บน Container ที่รันอยู่ตอนนี้เท่านั้น
ถ้าวันหลัง Redeploy Stack ของ NPM ใหม่ผ่าน Portainer (เช่นตอนอัปเดตเวอร์ชัน)
Container จะถูกสร้างใหม่และหลุดจาก Network นี้ทันที ต้องแก้ที่ตัว Stack ให้ถาวร:

1. Portainer → **Stacks** → เลือก Stack ของ Nginx Proxy Manager
2. เปิดไฟล์ Compose ของ Stack ดูชื่อ Service จริง (ตัวอย่างสมมติว่าชื่อ `app`)
   แล้วเพิ่ม:

   ```yaml
   services:
     app:                 # แก้ชื่อให้ตรงกับ Service จริงในไฟล์
       networks:
         - default
         - npm_proxy

   networks:
     npm_proxy:
       external: true
   ```

3. กด **Update the stack** — Portainer จะ Recreate Container แต่ครั้งนี้
   `npm_proxy` จะติดมาด้วยถาวร ไม่หลุดอีก

---

## เมื่อ Deploy App ใหม่ (เช่น PR-Robot, App02, ...) ในอนาคต

Compose ของทุก App ต้องทำแบบเดียวกัน:

- Service **Web**: อยู่ทั้งใน Network ภายในของตัวเอง (เช่น `pr-robot-uat_internal`)
  และ Network กลาง `npm_proxy` (`external: true`) — เพื่อให้ NPM Route เข้าถึงได้
- Service **DB**: อยู่ใน Network ภายในของตัวเองเท่านั้น **ห้าม** เข้า `npm_proxy`
  และ **ห้าม** เปิด `ports:` ออก Host

ตั้งค่า Proxy Host ใน NPM โดยใส่ **Forward Hostname/IP = ชื่อ Container Web**
(เช่น `pr-robot-prod-web`) ไม่ใช่ IP หรือ `localhost` — เพราะ NPM คุยกับ App
ผ่านชื่อ Container ใน Docker Network เดียวกัน
