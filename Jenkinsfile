// =====================================================================
// Jenkins declarative pipeline for the DevOps AI Dashboard.
//
//   Checkout -> Backend tests -> Frontend lint+build -> Docker images
//            -> Deploy (main branch only) -> Smoke test
//
// Every build/test step runs INSIDE Docker (multi-stage Dockerfiles), so the
// Jenkins machine only needs Docker - no Python or Node.js installation.
// =====================================================================
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '15'))
        disableConcurrentBuilds()
    }

    environment {
        IMAGE_TAG = "${env.BUILD_NUMBER}"
        COMPOSE_PROJECT_NAME = 'devops-ai'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --pretty=format:"%h %s (%an)"'
            }
        }

        stage('Backend tests') {
            steps {
                // Runs ruff + pytest in the "test" stage of backend/Dockerfile
                sh 'docker build --target test -t devops-ai-backend:test-${IMAGE_TAG} ./backend'
            }
        }

        stage('Build images') {
            parallel {
                stage('Backend image') {
                    steps {
                        sh 'docker build --target runtime -t devops-ai-backend:${IMAGE_TAG} -t devops-ai-backend:latest ./backend'
                    }
                }
                stage('Frontend image') {
                    steps {
                        // npm ci + eslint + vite build happen inside the image build
                        sh 'docker build -t devops-ai-frontend:${IMAGE_TAG} -t devops-ai-frontend:latest ./frontend'
                    }
                }
            }
        }

        stage('Deploy') {
            when { anyOf { branch 'main'; expression { env.GIT_BRANCH?.endsWith('/main') } } }
            steps {
                sh 'docker compose up -d --no-build backend frontend'
            }
        }

        stage('Smoke test') {
            when { anyOf { branch 'main'; expression { env.GIT_BRANCH?.endsWith('/main') } } }
            steps {
                // Wait up to 60 s for the API to answer /api/health
                sh '''
                  for i in $(seq 1 12); do
                    if docker exec devops-backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"; then
                      echo "Backend healthy"; exit 0
                    fi
                    echo "waiting for backend ($i/12)"; sleep 5
                  done
                  docker logs --tail 50 devops-backend
                  exit 1
                '''
            }
        }
    }

    post {
        always {
            // Remove the throw-away test image; keep the release images.
            sh 'docker image rm devops-ai-backend:test-${IMAGE_TAG} || true'
        }
        success { echo "Build #${env.BUILD_NUMBER} succeeded" }
        failure { echo 'Build failed - open the DevOps AI Dashboard > Pipelines > Diagnose for an AI explanation.' }
    }
}
