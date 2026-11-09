# Running Jenkins locally

```bash
docker compose --profile ci up -d --build jenkins     # ~700 MB RAM while running
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

1. Open http://localhost:8081, paste the password, choose **Install suggested plugins**
   (the ones in plugins.txt are already installed) and create your admin user.
2. **New Item → Pipeline** named `devops-ai-dashboard`.
   *Pipeline script from SCM* → Git → your repository URL → branch `*/main` →
   Script Path `Jenkinsfile`.
3. Your name (top right) → **Security → API Token → Add new token**. Put it in
   `backend/.env`:
   ```
   JENKINS_URL=http://localhost:8081
   JENKINS_USER=your-admin-user
   JENKINS_TOKEN=the-token
   ```
4. Restart the backend. The Pipelines page lists the job; **Build** triggers it,
   and a failed build gets a **Diagnose** button that sends the console log to Gemini.

Stop Jenkins when you do not need it: `docker compose stop jenkins`.
