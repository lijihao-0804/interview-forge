"""Portable, versioned atomic technology mention extractor for archived job snapshots.

No network access or project-specific imports are used. Mentions are descriptive
text evidence; they are not automatically classified as required skills.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Any, Iterator

DICTIONARY_VERSION = "tech-atomic-v4.1.0-2026-11-17"
EXTRACTOR_VERSION = "technology-extractor-v4.1.0"
PARSER_VERSION = "ascii-boundary-aho-v1+context-guard-v3+preferred-heading-v1+unicode-offset-v1"
DEFAULT_SNAPSHOT_DATE = "2026-11-17"
DICT_SCHEMA = "technology-lexicon/1"

# Each row is canonical name | alternate spellings / exact aliases.
# Atomic products and frameworks are kept separate (e.g. LangChain != LangGraph).
VOCABULARY: dict[str, str] = {
    "programming_language": r"""
Assembly|assembly language|汇编语言
C|C language|C语言
C++|cpp|cplusplus|C plus plus|C/C++
C#|C sharp|Csharp
Java|JDK|JVM语言
Kotlin|Kotlin语言
Scala|Scala语言
Groovy|Groovy语言
Python|Python语言
Go|Golang|Go语言
Rust|Rust语言
JavaScript|ECMAScript|JS
TypeScript|TS语言|TS
PHP|PHP语言
Ruby|Ruby语言
Swift|Swift语言
Objective-C|Objective C|ObjC
Dart|Dart语言
R|R语言|R programming
Julia|Julia语言
MATLAB|MATLAB语言
Bash|Bash脚本
Shell|Shell脚本|shell scripting
PowerShell|PowerShell脚本
Perl|Perl语言
Lua|Lua语言
Erlang|Erlang语言
Elixir|Elixir语言
Haskell|Haskell语言
Clojure|Clojure语言
F#|F sharp
Fortran|Fortran语言
COBOL|Cobol语言
Delphi|Object Pascal
Visual Basic .NET|VB.NET|Visual Basic.NET
Solidity|Solidity语言
Zig|Zig语言
Nim|Nim语言
Crystal|Crystal语言
OCaml|Objective Caml
Lisp|Common Lisp
Scheme|Scheme语言
Prolog|Prolog语言
Ada|Ada语言
Apex|Salesforce Apex
ABAP|SAP ABAP
PL/SQL|PLSQL
T-SQL|Transact-SQL|Transact SQL
VBA|Visual Basic for Applications
V language|Vlang
SQL|SQL query language|Structured Query Language
""",
    "markup_style_language": r"""
HTML|HTML5
CSS|CSS3|层叠样式表
Sass|SCSS
Less CSS|LESS
XML|XML语言
JSON Schema|JSON Schema Draft
YAML|YML
TOML|TOML格式
Markdown|CommonMark
LaTeX|TeX
GraphQL SDL|GraphQL schema
Protocol Buffers schema|Protobuf schema|proto3
Avro IDL|Apache Avro schema
""",
    "backend_framework": r"""
Spring Boot|SpringBoot
Spring Cloud|SpringCloud
Spring Framework|Spring框架
Spring MVC|SpringMVC
MyBatis|MyBatis Plus|MyBatis-Plus
Hibernate|Hibernate ORM
Jakarta EE|Java EE|J2EE
Quarkus|Quarkus框架
Micronaut|Micronaut框架
Struts|Apache Struts
Vert.x|Vertx
Netty|Netty框架
Dubbo|Apache Dubbo
gRPC Java|grpc-java
Dropwizard|Dropwizard框架
Javalin|Javalin框架
Dagger|Dagger DI
Guice|Google Guice
Django|Django REST framework|Django REST Framework|DRF
Flask|Flask框架
FastAPI|Fast API
Starlette|Starlette框架
Sanic|Sanic框架
Tornado|Tornado框架
Pyramid Python|Pyramid framework
Falcon Python|Falcon framework
Pydantic|Pydantic v2
SQLAlchemy|SQLAlchemy ORM
Alembic|Alembic migration
Celery|Celery task queue
Dramatiq|Dramatiq Python
Litestar|Starlite Python
Hug Python|Hug framework
Bottle Python|Bottle.py
CherryPy|CherryPy framework
Node.js|NodeJS
Express.js|Express|ExpressJS
NestJS|Nest.js|Nest JS
Koa.js|Koa|KoaJS
Fastify|Fastify.js
Hono|Hono.js
AdonisJS|Adonis.js
LoopBack|LoopBack.js
Prisma ORM|Prisma
TypeORM|TypeORM ORM
Sequelize|Sequelize ORM
Drizzle ORM|Drizzle
Mongoose|Mongoose ODM
Knex.js|Knex
Objection.js|Objection ORM
Laravel|Laravel PHP
Symfony|Symfony PHP
ThinkPHP|Think PHP
Yii Framework|Yii2|Yii 2
CodeIgniter|CodeIgniter PHP
ASP.NET Core|ASP.NET Core MVC
.NET Core|dotnet core
ASP.NET Web API|ASP.NET WebAPI
Entity Framework Core|EF Core
Dapper ORM|Dapper
Blazor|Blazor Server
Gin Go|Gin-Gonic
Echo Go|labstack echo
Fiber Go|gofiber
Beego|BeeGo
Kratos Go|go-kratos
Hertz Go|CloudWeGo Hertz
Kitex|CloudWeGo Kitex
go-zero|go zero
Buffalo Go|gobuffalo
Revel Go|Revel framework
Ruby on Rails|Rails framework
Sinatra Ruby|Sinatra framework
Drogon C++|Drogon
oatpp|Oat++
Crow C++|Crow framework
Restify|Restify.js
Moleculer|Moleculer.js
""",
    "frontend_framework": r"""
React|React.js|ReactJS
Vue.js|Vue|VueJS|Vue 2|Vue 3
Angular|AngularJS
Svelte|SvelteKit
SolidJS|Solid.js
Qwik|Qwik City
Preact|Preact.js
Lit|LitElement
Ember.js|Ember
jQuery|jQuery UI
Next.js|NextJS
Nuxt.js|Nuxt|Nuxt 3
Remix|Remix.run
Gatsby|Gatsby.js
Astro|Astro.build
Vite|Vite.js
Webpack|webpack.js
Rollup|Rollup.js
esbuild|es-build
Turbopack|TurboPack
Parcel bundler|Parcel.js
Babel|Babel.js
SWC compiler|SWC
Rspack|RSpack
Rspress|Rspress.js
Tailwind CSS|TailwindCSS
Bootstrap CSS|Bootstrap framework|Bootstrap 4|Bootstrap 5
Bulma CSS|Bulma
Foundation CSS|Zurb Foundation
CSS Modules|CSS module
styled-components|styled components
Emotion CSS|Emotion.js
UnoCSS|Uno CSS
Windi CSS|WindiCSS
Ant Design|AntD
Ant Design Vue|Antdv
Element Plus|Element-Plus
Element UI|ElementUI
Arco Design|ArcoDesign
Material UI|MUI React
Chakra UI|ChakraUI
shadcn/ui|shadcn ui
Radix UI|Radix Primitives
Headless UI|HeadlessUI
PrimeReact|Prime React
PrimeVue|Prime Vue
Vuetify|Vuetify.js
Naive UI|NaiveUI
Pinia|Pinia store
Vuex|Vuex store
Redux|Redux Toolkit|RTK
MobX|MobX state tree
Zustand|Zustand store
Recoil|Recoil state
Jotai|Jotai state
TanStack Query|React Query|Vue Query
SWR|Vercel SWR
Apollo Client|Apollo GraphQL Client
Relay|Relay GraphQL
Storybook|Storybook.js
Framer Motion|FramerMotion
Three.js|ThreeJS
Babylon.js|BabylonJS
D3.js|D3
ECharts|Apache ECharts
Highcharts|Highcharts.js
Chart.js|ChartJS
WebGL|WebGL 2
WebGPU|WebGPU API
""",
    "mobile_framework": r"""
Android SDK|Android Software Development Kit
iOS SDK|iOS Software Development Kit
SwiftUI|Swift UI
UIKit|UI Kit iOS
Jetpack Compose|Android Compose
Android Jetpack|Jetpack Android
Flutter|Flutter framework
React Native|ReactNative
Expo React Native|Expo
uni-app|uniapp
Taro framework|Taro
WeChat Mini Program|微信小程序
HarmonyOS|鸿蒙系统|OpenHarmony
ArkTS|Ark TypeScript
ArkUI|鸿蒙 ArkUI
Kotlin Multiplatform|KMP
Compose Multiplatform|Compose for Multiplatform
Xamarin|Xamarin.Forms
.NET MAUI|MAUI
Capacitor|Ionic Capacitor
Apache Cordova|Cordova
Ionic Framework|Ionic
CocoaPods|Cocoa Pods
Gradle Android|Android Gradle Plugin|AGP
""",
    "ai_ml_framework": r"""
PyTorch|PyTorch Lightning
TensorFlow|TensorFlow 2|TF 2
Keras|Keras 3
JAX|JAX library
Flax NNX|Flax
Haiku JAX|dm-haiku
scikit-learn|sklearn|Scikit Learn
XGBoost|XGBoost4J
LightGBM|Light GBM
CatBoost|Cat Boost
ONNX|Open Neural Network Exchange
ONNX Runtime|ORT
TensorRT|NVIDIA TensorRT
TensorRT-LLM|TensorRT LLM|TRT-LLM
OpenVINO|OpenVINO toolkit
Core ML|CoreML
TensorFlow Lite|TFLite
Transformers|Hugging Face Transformers|HF Transformers
Diffusers|Hugging Face Diffusers
Tokenizers|Hugging Face Tokenizers
Hugging Face Datasets|HF Datasets
Accelerate|Hugging Face Accelerate
TRL|Transformer Reinforcement Learning
PEFT|Parameter-Efficient Fine-Tuning
bitsandbytes|bitsandbytes library
vLLM|vLLM engine
SGLang|SGLang runtime
LMDeploy|LM Deploy
Text Generation Inference|TGI|Hugging Face TGI
llama.cpp|llama cpp
Ollama|Ollama runtime
Triton Inference Server|NVIDIA Triton Inference Server|NVIDIA Triton
Triton language|OpenAI Triton|Triton compiler|Triton kernel
Triton unresolved mention|Triton
BentoML|Bento ML
TorchServe|PyTorch Serve
DeepSpeed|DeepSpeed training
Megatron-LM|Megatron LM
Fully Sharded Data Parallel|FSDP
Colossal-AI|ColossalAI
MindSpore|MindSpore framework
PaddlePaddle|PaddlePaddle framework
PaddleNLP|Paddle NLP
OneFlow|OneFlow framework
Jittor|计图
Apache MXNet|MXNet
Caffe|BVLC Caffe
PyTorch Geometric|PyG
DGL|Deep Graph Library
cuML|RAPIDS cuML
cuDF|RAPIDS cuDF
RAPIDS|NVIDIA RAPIDS
Ray Tune|Tune library
Ray platform|Ray distributed|Ray
Optuna|Optuna optimization
Hyperopt|Hyperopt tuning
Nevergrad|Nevergrad optimizer
""",
    "agent_framework": r"""
LangChain|LangChain framework
LangGraph|LangGraph framework
LlamaIndex|GPT Index
Microsoft Semantic Kernel|Semantic Kernel
AutoGen|Microsoft AutoGen
CrewAI|Crew AI
Haystack|deepset Haystack
DSPy|Declarative Self-improving Python
PydanticAI|Pydantic AI
AutoGPT|Auto-GPT
Flowise|FlowiseAI
Dify|Dify platform
Coze|扣子
FastGPT|Fast GPT
LlamaStack|Llama Stack
Langfuse|Langfuse observability
LangSmith|LangSmith platform
Prompt flow|Azure Prompt flow
Langflow|Langflow platform
OpenHands|OpenDevin
Smolagents|smol-agents
Browser Use|browser-use
MCP|Model Context Protocol
""",
    "ai_model_platform": r"""
GPT-4|GPT-4o|GPT-4.1|GPT-4 Turbo
GPT-3.5|GPT-3.5 Turbo
Claude|Claude 3|Claude 3.5|Claude 4
Gemini|Gemini Pro|Gemini 1.5|Gemini 2.0
ChatGPT|Chat GPT|OpenAI ChatGPT
OpenAI API|OpenAI API platform
DeepSeek|DeepSeek-V2|DeepSeek-V3|DeepSeek-R1
Qwen|通义千问|Qwen2|Qwen2.5|Qwen3
Llama 2|Llama2
Llama 3|Llama3
Mistral|Mistral AI models
Mixtral|Mixtral MoE
GLM|ChatGLM|智谱 GLM
Yi model|零一万物 Yi
Baichuan model|百川大模型
Kimi|Moonshot model
InternLM|书生·浦语
MiniCPM|MiniCPM-V
Phi model|Phi-3|Phi-4
Gemma|Gemma 2|Gemma 3
Falcon LLM|Falcon model
ERNIE Bot|文心一言|文心大模型
Hunyuan model|混元大模型|腾讯混元
Doubao model|豆包大模型|Doubao LLM
Step model|阶跃星辰模型
Command R|Cohere Command R
Stable Diffusion|SDXL
FLUX model|FLUX.1
DALL-E|DALL·E
Imagen|Google Imagen
Wan model|通义万相|Wan 2.1
HunyuanVideo|混元视频
Sora model|OpenAI Sora
Qwen-VL|通义千问VL
Qwen-Audio|通义千问Audio
LLaVA|LLaVA model
InternVL|InternVL2
MiniCPM-Vision|MiniCPM Vision
Whisper model|OpenAI Whisper
SenseVoice|FunAudioLLM SenseVoice
""",
    "ai_concept_method": r"""
Large Language Model|LLM|large language models|大语言模型|大模型
Generative AI|GenAI|生成式人工智能
Retrieval-Augmented Generation|RAG|检索增强生成
GraphRAG|Graph RAG
Agentic workflow|agentic AI|智能体工作流
AI agent|AI Agent|智能体
Multi-agent system|multi agent|多智能体
Tool calling|tool call|工具调用|函数调用
Function calling|function call
Prompt engineering|提示词工程|prompt engineering
Prompt tuning|提示微调
In-context learning|ICL|上下文学习
Chain of thought|CoT|思维链
ReAct prompting
Tree of Thoughts|ToT
Embedding|embeddings|向量嵌入
Vector search|向量检索
Reranking|re-ranking|重排序|重排
Semantic search|语义检索
Knowledge graph|知识图谱
Multimodal model|multimodal AI|多模态模型|多模态
Vision-language model|VLM|视觉语言模型
Vision-language-action model|VLA model|视觉语言动作模型
Diffusion model|diffusion models|扩散模型
Transformer architecture|Transformer|transformer模型
Mixture of Experts|MoE|专家混合
Attention mechanism|self-attention|注意力机制
KV cache|key-value cache
Speculative decoding|speculative sampling|投机解码
Continuous batching|continuous batch
PagedAttention|paged attention
Quantization|quantisation|量化
Pruning|model pruning|剪枝
Knowledge distillation|distillation|模型蒸馏
Supervised fine-tuning|SFT|监督微调
Fine-tuning|fine tuning|微调
LoRA|Low-Rank Adaptation
QLoRA|Quantized LoRA
Preference optimization|偏好优化
Direct Preference Optimization|DPO
Group Relative Policy Optimization|GRPO
Reinforcement Learning from Human Feedback|RLHF|人类反馈强化学习
Reinforcement Learning from AI Feedback|RLAIF|AI反馈强化学习
Proximal Policy Optimization|PPO
Reward model|奖励模型|reward modeling
Reward shaping|奖励塑形|奖励函数
ORPO|Odds Ratio Preference Optimization
KTO|Kahneman-Tversky Optimization
SimPO|Simple Preference Optimization
IPO|Implicit Preference Optimization
RLVR|reinforcement learning with verifiable rewards
Test-time compute|test time scaling|推理时扩展
Synthetic data|synthetic training data|合成数据
Data curation|training data curation|训练数据治理
Model alignment|alignment training|模型对齐
Constitutional AI|CAI
Safety alignment|安全对齐
Red teaming|red-team testing|红队测试
Guardrails|AI guardrails|安全护栏
Context window|context length|上下文窗口
Long-context modeling|长上下文
Inference optimization|推理优化
KV compression|KV cache compression
Model serving|模型服务
Fine-grained evaluation|模型评测
Benchmarking|benchmark evaluation|基准评测
Continual learning|持续学习
Federated learning|联邦学习
Transfer learning|迁移学习
Self-supervised learning|自监督学习
Contrastive learning|对比学习
Graph neural network|GNN|图神经网络
Recommender system|recommendation system|推荐系统
Computer vision|计算机视觉
Natural language processing|NLP|自然语言处理
Automatic speech recognition|ASR|语音识别
Text-to-speech|TTS|语音合成
""",
    "ai_evaluation": r"""
lm-evaluation-harness|lm eval harness|EleutherAI LM Evaluation Harness
OpenCompass|Open Compass
MMLU|Massive Multitask Language Understanding
C-Eval|CEval|C-Eval benchmark
CMMLU|Chinese Massive Multitask Language Understanding
HumanEval|Human Eval
MBPP|Mostly Basic Python Problems
BFCL|Berkeley Function Calling Leaderboard
AgentBench|Agent Bench
GAIA benchmark|GAIA
HELM benchmark
Ragas|RAGAS
DeepEval|Deep Eval
promptfoo|Promptfoo
TruLens|TruLens evaluation
Arize Phoenix|Phoenix AI observability
UpTrain|UpTrain evaluation
Lighteval|LightEval
BigBench|BIG-bench
MT-Bench|MTBench
""",
    "database_search": r"""
MySQL|MySQL 8
PostgreSQL|Postgres|PostgreSQL database
MariaDB|Maria DB
Oracle Database|Oracle DB
Microsoft SQL Server|MS SQL Server|MSSQL
SQLite|SQLite database
TiDB|TiDB database
CockroachDB|Cockroach DB
YugabyteDB|Yugabyte DB
OceanBase|OceanBase database
PolarDB|Polar DB
GaussDB|openGauss|Gauss DB
KingbaseES|人大金仓
Dameng Database|达梦数据库|DM8
IBM Db2|DB2
Teradata|Teradata database
Snowflake|Snowflake Data Cloud
Google BigQuery|BigQuery
Amazon Redshift|Redshift
ClickHouse|ClickHouse database
DuckDB|Duck DB
Apache Doris|Doris OLAP
StarRocks|Star Rocks
Databend|Databend database
Greenplum|Greenplum Database
Redis|Redis cache
Valkey|Valkey cache
Memcached|Memcached cache
Aerospike|Aerospike DB
DragonflyDB|Dragonfly DB
RocksDB|Rocks DB
LevelDB|Level DB
LMDB|Lightning Memory-Mapped Database
MongoDB|Mongo DB
Apache Cassandra|Cassandra DB
Apache HBase|HBase
Amazon DynamoDB|DynamoDB
Couchbase|Couchbase Server
CouchDB|Apache CouchDB
Elasticsearch|ElasticSearch
OpenSearch|Open Search
Apache Solr|Solr search
Milvus|Milvus vector database
Weaviate|Weaviate vector database
Pinecone database|Pinecone vector DB
Qdrant|Qdrant vector database
ChromaDB|Chroma vector database
pgvector|pg_vector
Vespa engine|Vespa.ai
Neo4j|Neo4j graph database
NebulaGraph|Nebula Graph
TigerGraph|Tiger Graph
HugeGraph|Apache HugeGraph
JanusGraph|Janus Graph
ArangoDB|Arango DB
""",
    "data_engineering": r"""
Apache Hadoop|Hadoop
Apache Spark|Spark
PySpark|PySpark API
Apache Flink|Flink
Apache Kafka|Kafka
Apache Pulsar|Pulsar messaging
RabbitMQ|Rabbit MQ
RocketMQ|Apache RocketMQ
ZeroMQ|ØMQ
Redpanda|Redpanda streaming
Apache Hive|Hive
Apache Hudi|Hudi
Apache Iceberg|Iceberg table format
Delta Lake|Delta Lakehouse
Apache Paimon|Paimon
Debezium|Debezium CDC
Apache Flume|Flume
Apache Sqoop|Sqoop
Airbyte|Airbyte data integration
Fivetran|Fivetran connector
dbt|data build tool|dbt Core
Trino|Trino SQL
Presto|PrestoDB
Apache Druid|Druid
Apache Pinot|Pinot OLAP
Apache Beam|Beam SDK
Apache NiFi|NiFi
Flink CDC|FlinkCDC
Spark Structured Streaming|Structured Streaming
Kafka Streams|Kafka Streams API
Apache Samza|Samza
Apache Storm|Storm stream processing
Apache Kylin|Kylin OLAP
Apache Atlas|Atlas metadata
DataHub|DataHub metadata
OpenMetadata|Open Metadata
Amundsen|Lyft Amundsen
Apache Parquet|Parquet format
Apache ORC|ORC file format
Apache Arrow|Arrow format
Apache Avro|Avro
Hudi MOR|Hudi Merge On Read
Iceberg REST Catalog|Iceberg catalog
""",
    "cloud_platform": r"""
Amazon Web Services|AWS|AWS cloud
Microsoft Azure|Azure cloud
Google Cloud Platform|GCP cloud|Google Cloud
Alibaba Cloud|阿里云
Tencent Cloud|腾讯云
Huawei Cloud|华为云
Baidu AI Cloud|百度智能云
Oracle Cloud Infrastructure|OCI cloud
IBM Cloud|IBM cloud
Cloudflare|Cloudflare platform
Amazon EC2|EC2
Amazon S3|S3 object storage
Amazon EKS|EKS
Amazon ECS|ECS
AWS Lambda|Lambda serverless
AWS SageMaker|Amazon SageMaker
Amazon Bedrock|AWS Bedrock
Azure OpenAI Service|Azure OpenAI
Azure Kubernetes Service|AKS
Google Kubernetes Engine|GKE
Google Cloud Storage|GCS
Google Cloud Run|Cloud Run
Google Vertex AI|Vertex AI
Azure Machine Learning|Azure ML
Alibaba ACK|阿里云 ACK
Tencent TKE|腾讯云 TKE
Huawei CCE|华为云 CCE
""",
    "infrastructure_tool": r"""
Linux|GNU/Linux
Ubuntu|Ubuntu Linux
Debian|Debian Linux
Red Hat Enterprise Linux|RHEL
CentOS|CentOS Linux
Rocky Linux|RockyLinux
AlmaLinux|Alma Linux
Alpine Linux|Alpine
SUSE Linux Enterprise|SLES
FreeBSD|Free BSD
Windows Server|Windows Server OS
Docker|Docker Engine
Docker Compose|docker-compose
Slurm Workload Manager|Slurm
Podman|Podman container engine
containerd|container runtime containerd
CRI-O|CRI O
Kubernetes|K8s
Helm|Helm charts
Kustomize|Kustomize Kubernetes
Istio|Istio service mesh
Linkerd|Linkerd service mesh
Envoy Proxy|Envoy
Nginx|NGINX
HAProxy|HAProxy load balancer
Traefik|Traefik Proxy
Caddy Server|Caddy
Kong Gateway|Kong API Gateway
Apache APISIX|APISIX
Higress|Higress gateway
Terraform|HashiCorp Terraform
OpenTofu|Open Tofu
Pulumi|Pulumi IaC
Ansible|Ansible automation
Chef Infra|Chef configuration management
Puppet|Puppet configuration management
SaltStack|Salt
Packer|HashiCorp Packer
AWS CloudFormation|CloudFormation
AWS CDK|Cloud Development Kit
Git|Git version control
GitHub Actions|GitHub workflow
GitLab CI/CD|GitLab CI
Jenkins|Jenkins CI
CircleCI|Circle CI
Buildkite|Buildkite CI
Argo CD|ArgoCD
Flux CD|FluxCD
Spinnaker|Spinnaker CD
Tekton|Tekton Pipelines
Bazel|Bazel build
Buck2|Buck build
CMake|CMake build system
Ninja build|Ninja
GNU Make|Makefile
Meson build|Meson
Gradle|Gradle build
Maven|Apache Maven
SBT|Scala Build Tool
Nix|Nix package manager
Guix|GNU Guix
""",
    "observability_tool": r"""
Prometheus|Prometheus monitoring
Grafana|Grafana dashboard
OpenTelemetry|OTel
Jaeger|Jaeger tracing
Zipkin|Zipkin tracing
Elasticsearch Logstash Kibana|ELK stack
OpenSearch Dashboards|OpenSearch dashboard
Loki|Grafana Loki
Datadog|Datadog APM
New Relic|NewRelic
Splunk|Splunk Observability
Sentry|Sentry error monitoring
Zabbix|Zabbix monitoring
Nagios|Nagios monitoring
Apache SkyWalking|SkyWalking
Falco|Falco runtime security
PagerDuty|PagerDuty incident management
VictoriaMetrics|Victoria Metrics
Thanos|Thanos monitoring
Mimir|Grafana Mimir
""",
    "network_protocol": r"""
HTTP|HTTP protocol
HTTPS|HTTP Secure
HTTP/2|HTTP 2
HTTP/3|HTTP 3
REST API|RESTful API|REST
gRPC|gRPC protocol
GraphQL|GraphQL API
WebSocket|WebSockets
MQTT|MQ Telemetry Transport
AMQP|Advanced Message Queuing Protocol
DNS|Domain Name System
TCP/IP|TCP IP
QUIC|QUIC protocol
SSH|Secure Shell
SFTP|SSH File Transfer Protocol
FTP|File Transfer Protocol
UDP|User Datagram Protocol
NTP|Network Time Protocol
SIP|Session Initiation Protocol
RTP|Real-time Transport Protocol
OPC UA|OPC Unified Architecture
Modbus|Modbus TCP
OpenAPI|OpenAPI Specification
Swagger|Swagger API
JSON-RPC|JSON RPC
XML-RPC|XML RPC
Apache Thrift|Thrift RPC
Protocol Buffers|Protobuf
FlatBuffers|FlatBuffers serialization
Cap'n Proto|Capn Proto
MessagePack|msgpack
CBOR|Concise Binary Object Representation
WebRTC|Web Real-Time Communication
WebTransport|Web Transport API
IPsec|IP Security
TLS|Transport Layer Security
SSL|Secure Sockets Layer
WireGuard|WireGuard VPN
InfiniBand|IB network
RoCE|RDMA over Converged Ethernet
RDMA|Remote Direct Memory Access
""",
    "security_identity": r"""
OAuth 2.0|OAuth2
OpenID Connect|OIDC
SAML|SAML 2.0
JSON Web Token|JWT
Kerberos|Kerberos authentication
LDAP|Lightweight Directory Access Protocol
RBAC|Role-Based Access Control
ABAC|Attribute-Based Access Control
Zero Trust|零信任
Mutual TLS|mTLS
Public Key Infrastructure|PKI
Identity and Access Management|IAM
Web Application Firewall|WAF
OWASP Top 10|OWASP
WebAuthn|FIDO2 WebAuthn
FIDO2|FIDO 2
SAST|Static Application Security Testing
DAST|Dynamic Application Security Testing
SCA|Software Composition Analysis
SBOM|Software Bill of Materials
Burp Suite|Burp
Wireshark|Wireshark analyzer
Nmap|Network Mapper
Metasploit|Metasploit Framework
HashiCorp Vault|Vault secrets
Open Policy Agent|OPA policy
Kyverno|Kubernetes policy engine
OPA Gatekeeper|Gatekeeper policy
Ghidra|NSA Ghidra
""",
    "gpu_hardware": r"""
CPU|Central Processing Unit
GPU|Graphics Processing Unit|图形处理器
NPU|Neural Processing Unit|神经网络处理器
TPU|Tensor Processing Unit
FPGA|Field-Programmable Gate Array
ASIC|Application-Specific Integrated Circuit
SoC|System on Chip|System-on-Chip
MCU|Microcontroller Unit|微控制器
DSP|Digital Signal Processor
ARM architecture|ARM架构|AArch64|ARM64
x86 architecture|x86_64|AMD64
RISC-V|RISC V|RISCV
MIPS architecture|MIPS处理器
PowerPC|Power PC
LoongArch|龙芯架构
SPARC|SPARC architecture
CUDA|CUDA programming
cuDNN|CUDA Deep Neural Network library
cuBLAS|CUDA Basic Linear Algebra Subprograms
NCCL|NVIDIA Collective Communications Library
NVLink|NVLink interconnect
NVSwitch|NVSwitch fabric
ROCm|AMD ROCm
HIP|Heterogeneous-Compute Interface for Portability
MIOpen|AMD MIOpen
oneAPI|Intel oneAPI
SYCL|SYCL programming
OpenCL|Open Computing Language
Vulkan Compute|Vulkan compute shader
DirectML|Direct Machine Learning
OpenACC|OpenACC programming
OpenMP|Open Multi-Processing
MPI|Message Passing Interface
UCX|Unified Communication X
PCI Express|PCIe
Compute Express Link|CXL
DDR memory|DDR4|DDR5
HBM memory|HBM|High Bandwidth Memory
GDDR memory|GDDR6|GDDR7
LPDDR memory|LPDDR4|LPDDR5
NVMe|Non-Volatile Memory Express
SATA|Serial ATA
UFS storage|Universal Flash Storage
eMMC|embedded MultiMediaCard
USB|Universal Serial Bus
I2C|I²C|Inter-Integrated Circuit
SPI bus|Serial Peripheral Interface
UART|Universal Asynchronous Receiver-Transmitter
CAN bus|Controller Area Network
LIN bus|Local Interconnect Network
JTAG|IEEE 1149.1
""",
    "embedded_platform": r"""
Embedded Linux|Linux embedded
FreeRTOS|Free RTOS
Zephyr RTOS|Zephyr
ThreadX|Azure RTOS ThreadX
VxWorks|VxWorks RTOS
QNX|QNX Neutrino
RT-Thread|RTThread
NuttX|Apache NuttX
ChibiOS|Chibi OS
AUTOSAR|AUTomotive Open System ARchitecture
Arduino|Arduino platform
ESP32|ESP-IDF
ESP8266|ESP8266 SDK
STM32|STM32Cube
Raspberry Pi|Raspberry Pi OS
Jetson platform|Jetson Orin|Jetson Nano
Yocto Project|Yocto
Buildroot|Buildroot Linux
U-Boot|Das U-Boot
OpenWrt|OpenWRT
Android Things|Android Things OS
TinyML|tiny machine learning
Edge AI|edge inference|端侧AI
CANopen|CAN Open
Device Tree|devicetree
eBPF|extended Berkeley Packet Filter
DPDK|Data Plane Development Kit
SPDK|Storage Performance Development Kit
VPP|Vector Packet Processing
P4 language|P4 programmable data plane
""",
    "hardware_design_tool": r"""
Verilog|Verilog HDL
SystemVerilog|System Verilog
VHDL|VHSIC Hardware Description Language
Chisel HDL|Chisel hardware construction language
Bluespec|Bluespec SystemVerilog
SystemC|System C
UVM|Universal Verification Methodology
SVA|SystemVerilog Assertions
Cocotb|Coroutine-based cosimulation testbench
Verilator|Verilog compiler
Synopsys VCS|VCS simulator
Cadence Xcelium|Xcelium simulator
QuestaSim|Questa
Vivado|AMD Vivado
Intel Quartus|Quartus Prime
Synopsys Design Compiler|Design Compiler
Synopsys PrimeTime|PrimeTime STA
Cadence Innovus|Innovus Implementation System
Cadence Genus|Genus Synthesis
Cadence Virtuoso|Virtuoso Design Platform
Synopsys IC Compiler II|ICC2
Calibre DRC|Siemens Calibre
OpenROAD|OpenROAD flow
Yosys|Yosys synthesis
OpenLane|OpenLane flow
DFT|Design for Test
LEC|Logical Equivalence Checking
STA|Static Timing Analysis
Place and Route|P&R|place-and-route
Altium Designer|Altium
KiCad|KiCad EDA
OrCAD|Cadence OrCAD
Cadence Allegro|Allegro PCB Designer
PADS|PADS PCB
LTspice|LTspice simulator
Keysight ADS|Advanced Design System
Ansys HFSS|HFSS
CST Studio Suite|CST Microwave Studio
Ansys Icepak|Icepak thermal simulation
Ansys Fluent|Fluent CFD
""",
    "hardware_interface_radio": r"""
Wi-Fi|WiFi|IEEE 802.11
Bluetooth|Bluetooth Classic
Bluetooth Low Energy|BLE
Zigbee|ZigBee
Thread protocol|Thread IoT
NFC|Near-Field Communication
5G NR|5G New Radio
LTE|4G LTE
NB-IoT|Narrowband IoT
LoRaWAN|LoRa WAN
UWB|Ultra-Wideband
Ethernet|IEEE 802.3
PCIe Gen5|PCI Express Gen 5
PCIe Gen6|PCI Express Gen 6
USB Type-C|USB-C
DisplayPort|DP interface
HDMI|High-Definition Multimedia Interface
MIPI CSI|MIPI Camera Serial Interface
MIPI DSI|MIPI Display Serial Interface
I3C|Improved Inter-Integrated Circuit
I2S|Inter-IC Sound
JESD204|JESD204B|JESD204C
SerDes|Serializer/Deserializer
AXI bus|Advanced eXtensible Interface
AMBA|Advanced Microcontroller Bus Architecture
Wishbone bus|Wishbone
""",
    "testing_development_tool": r"""
pytest|pytest testing
unittest Python|Python unittest
JUnit|JUnit 5
TestNG|TestNG framework
Mockito|Mockito Java
Jest|Jest testing
Mocha JS|Mocha testing
Vitest|Vitest testing
Cypress|Cypress testing
Playwright|Microsoft Playwright
Selenium|Selenium WebDriver
Appium|Appium mobile testing
Robot Framework|Robot Framework testing
Locust|Locust load testing
k6|Grafana k6
Apache JMeter|JMeter
Gatling|Gatling load testing
Postman|Postman API testing
Newman CLI|Newman Postman
Pact contract testing|Pact
Karate DSL|Karate API testing
GTest|Google Test|GoogleTest
Catch2|Catch 2
CppUTest|Cpp U Test
Google Benchmark|benchmark library
Valgrind|Valgrind profiler
AddressSanitizer|ASan
ThreadSanitizer|TSan
""",
    "developer_tool": r"""
Visual Studio Code|VS Code|VSCode
IntelliJ IDEA|IntelliJ
PyCharm|PyCharm IDE
Vim|Vim editor
Neovim|NeoVim
Emacs|GNU Emacs
Eclipse IDE|Eclipse
Visual Studio IDE|Microsoft Visual Studio
Xcode|Apple Xcode
Android Studio|AndroidStudio
Jupyter Notebook|Jupyter
JupyterLab|Jupyter Lab
IPython|Interactive Python
Conda|Anaconda
Miniconda|Miniconda Python
Poetry Python|Poetry package manager
uv Python|Astral uv
pip|Python pip
Mamba package manager|mamba
Pipenv|Pipenv Python
RStudio|Posit RStudio
GitHub Copilot|Copilot coding assistant
Tabnine|Tabnine AI
Codeium|Windsurf Codeium
Cursor IDE|Cursor editor
Sourcegraph Cody|Cody AI
""",
    "business_analytics": r"""
Microsoft Excel|Excel|MS Excel
Tableau|Tableau Desktop|Tableau Server|Tableau Prep
Microsoft Power BI|Power BI|PowerBI|Power BI Desktop|Power BI Service
IBM SPSS Statistics|SPSS|IBM SPSS
SAS Statistical Software|SAS|SAS Base|SAS Studio|SAS Viya
Stata|Stata/MP|Stata SE
Alteryx|Alteryx Designer|Alteryx Server
Looker|Google Looker
QlikView|Qlik View
Qlik Sense|QlikSense
Apache Superset|Superset
Metabase|Metabase analytics
Microsoft Power Query|Power Query|Excel Power Query
""",
    "design_dcc": r"""
Figma|Figma Design
Axure RP|Axure
Sketch|Sketch app
Adobe Photoshop|Photoshop
Adobe Illustrator|Illustrator
Adobe XD|XD design tool
InVision|InVision Studio
Miro|Miro board
Canva|Canva design
Adobe After Effects|After Effects
Adobe Premiere Pro|Premiere Pro|Adobe Premiere
DaVinci Resolve|DaVinci
Blender|Blender 3D
Autodesk 3ds Max|3ds Max|3D Studio Max|3dsmax|3D Max
Autodesk Maya|Maya
Autodesk AutoCAD|AutoCAD|Auto CAD
SideFX Houdini|Houdini
Maxon ZBrush|ZBrush
Maxon Cinema 4D|Cinema 4D|C4D
""",
    "game_development": r"""
Unity|Unity3D|Unity Engine
Unreal Engine|Unreal|Unreal Engine 4|UE4|Unreal Engine 5|UE5
Godot Engine|Godot
Cocos Creator|CocosCreator
Cocos2d-x|Cocos2d|Cocos2dx
CryEngine|Cry Engine
GameMaker|GameMaker Studio
Audiokinetic Wwise|Wwise
FMOD|FMOD Studio
""",
}

CATEGORY_LABELS = {
    "programming_language": ("编程语言", "language"),
    "markup_style_language": ("标记与样式语言", "language"),
    "backend_framework": ("后端框架与库", "framework"),
    "frontend_framework": ("前端框架与库", "framework"),
    "mobile_framework": ("移动端框架与平台", "framework"),
    "ai_ml_framework": ("机器学习框架与推理工具", "framework"),
    "agent_framework": ("Agent框架与编排工具", "framework"),
    "ai_model_platform": ("模型产品与平台", "platform_product"),
    "ai_concept_method": ("AI技术概念与方法", "concept"),
    "ai_evaluation": ("模型评测工具与基准", "tool"),
    "database_search": ("数据库与搜索系统", "platform_product"),
    "data_engineering": ("数据处理与流式平台", "platform_product"),
    "cloud_platform": ("云平台与云服务", "platform_product"),
    "infrastructure_tool": ("基础设施与交付工具", "tool"),
    "observability_tool": ("可观测性与运维工具", "tool"),
    "network_protocol": ("网络协议与序列化", "protocol"),
    "security_identity": ("安全与身份技术", "concept"),
    "gpu_hardware": ("计算硬件与加速接口", "hardware"),
    "embedded_platform": ("嵌入式与边缘平台", "platform_product"),
    "hardware_design_tool": ("芯片与硬件设计工具", "tool"),
    "hardware_interface_radio": ("总线、接口与无线技术", "hardware"),
    "testing_development_tool": ("测试与性能工具", "tool"),
    "developer_tool": ("开发工具与编程环境", "tool"),
    "business_analytics": ("数据分析与BI工具", "tool"),
    "design_dcc": ("设计、原型与数字内容工具", "tool"),
    "game_development": ("游戏引擎与音频中间件", "platform_product"),
}

GUARD_PATTERNS = {
    "go_language": re.compile(r"golang|go\s*(?:语言|开发|编程|后端|服务|微服务|框架|程序|工程|language|programming|developer)|(?:使用|掌握|熟悉|精通|开发|编写)\s*go\b|(?:python|java|c\+\+|rust)(?:\s*[,/、及和与]\s*(?:python|java|c\+\+|go|rust))*\s*[,/、及和与]\s*go\b|go\s*(?:[,/&]|and)\s*(?:python|java|rust|c\+\+)", re.I),
    "c_language": re.compile(r"c\s*(?:语言|开发|编程|language|programming)|c\s*/\s*c\+\+|(?:使用|掌握|熟悉|精通|开发|编写)\s*c\b|(?:c\+\+|java|python)\s*(?:和|及|/|、|,|and)\s*c\b", re.I),
    "r_language": re.compile(r"r\s*(?:语言|编程|开发|language|programming)|r\s*/\s*(?:python|java)|(?:使用|掌握|熟悉|精通)\s*r\b|rstudio|rmarkdown", re.I),
    "js_acronym": re.compile(r"(?:javascript|js\s*(?:开发|工程|语言|框架|代码)|(?:使用|熟悉|掌握|精通)\s*js\b|js\s*(?:/|、|,|和|and)\s*(?:html|css|ts))", re.I),
    "ts_acronym": re.compile(r"(?:typescript|ts\s*(?:开发|工程|语言|类型)|(?:使用|熟悉|掌握|精通)\s*ts\b|ts\s*(?:/|、|,|和|and)\s*(?:js|javascript))", re.I),
    "react_framework": re.compile(r"react(?:\.js|js|\s*(?:native|框架|组件|开发|项目|生态|framework|component|developer|application|app))|(?:使用|掌握|精通)\s*react\b|react\s*(?:,|/|&|and)\s*(?:vue|angular|svelte|next\.js)|(?:vue|angular|svelte)\s*(?:,|/|&|and)\s*react\b", re.I),
    "flask_framework": re.compile(r"flask\s*(?:框架|api|服务|应用|开发|项目|framework|api|service|application|app|development)|(?:python|rest|web)\s+flask|(?:使用|掌握|精通)\s*flask\b|python\s*[,/]\s*flask|flask\s*(?:,|/|&|and)\s*(?:fastapi|django)|(?:fastapi|django)\s*(?:,|/|&|and)\s*flask\b", re.I),
    "spark_platform": re.compile(r"apache\s+spark|pyspark|spark\s*(?:sql|streaming|框架|集群|计算|开发|任务|作业|生态|framework|cluster|job|development)|(?:使用|掌握|基于)\s*spark\b|hadoop\s*/\s*spark|spark\s*/\s*(?:hive|flink|kafka)|(?:hadoop|flink|kafka)\s*(?:,|/|&|and)\s*spark\b", re.I),
    "hive_platform": re.compile(r"apache\s+hive|hive\s*(?:sql|ql|数仓|数据仓库|metastore|开发|warehouse|table|query)|(?:使用|掌握)\s*hive\b|hadoop\s*/\s*spark\s*/\s*hive|spark\s*/\s*hive|hive\s*(?:,|/|&|and)\s*(?:spark|hadoop|flink)|spark\s*(?:,|/|&|and)\s*hive\b", re.I),
    "ray_platform": re.compile(r"ray\s*(?:serve|tune|rllib|框架|集群|actor|任务|计算|cluster|framework|developer|runtime)|(?:使用|掌握|基于)\s*ray\b|ray\.io|ray\s*(?:,|/|&|and)\s*(?:slurm|kubernetes|spark|dask|mlflow|model\s+serving)|(?:slurm|kubernetes|spark|dask|mlflow)\s*(?:,|/|&|and)\s*ray\b", re.I),
    "rust_language": re.compile(r"rust\s*(?:语言|开发|编程|项目|工程|生态|language|programming|developer)|(?:使用|掌握|精通)\s*rust\b|cargo\s+rust|rust\s*(?:/|,|&|and)\s*(?:c\+\+|go|python)|(?:c\+\+|go|python)\s*(?:/|,|&|and)\s*rust\b", re.I),
    "ruby_language": re.compile(r"ruby\s*(?:语言|开发|编程|on\s+rails|language|programming|developer)|(?:使用|掌握|精通)\s*ruby\b|rails\s*/\s*ruby", re.I),
    "swift_language": re.compile(r"swift\s*(?:语言|开发|编程|ui|ios|language|programming|developer)|(?:使用|掌握|精通)\s*swift\b|swift\s*(?:/|,|&|and)\s*(?:ios|uikit|swiftui)", re.I),
    "bootstrap_css": re.compile(r"bootstrap\s*(?:css|框架|样式|页面|4|5)|(?:使用|熟悉|掌握)\s*bootstrap\b", re.I),
    "sas_statistics": re.compile(r"sas\s*(?:(?:stat(?:istics?)?|statistical|analytics|programming|software|studio|base|viya|data|proc)\b|(?:进行)?(?:统计|数据分析|软件|编程|语言|建模))|(?:使用|熟悉|掌握|精通)\s*sas\b|(?:spss|stata|python|r)\s*(?:,|/|、|和|and)\s*sas\b", re.I),
    "sketch_design": re.compile(r"sketch\s*(?:软件|工具|app|application|design|UI|UX|prototype|原型|界面|插件)|(?:使用|熟悉|掌握|精通)\s*sketch\b|(?:figma|axure|photoshop|illustrator)\s*(?:,|/|&|and|、|和)\s*sketch\b|sketch\s*(?:,|/|&|and|、|和)\s*(?:figma|axure|photoshop|illustrator)", re.I),
    "unity_engine": re.compile(r"unity\s*(?:engine|3d|引擎|游戏|开发|项目|developer|game)|(?:使用|熟悉|掌握|精通|开发|基于)\s*unity\b|unity\s*(?:,|/|&|and|、|和)\s*(?:unreal|godot|cocos|cryengine|gamemaker)|(?:unreal|godot|cocos|cryengine|gamemaker)\s*(?:,|/|&|and|、|和)\s*unity\b", re.I),
    "unreal_engine": re.compile(r"unreal\s*(?:engine|引擎|游戏|开发|project|developer)|(?:使用|熟悉|掌握|精通)\s*unreal\b|\bue\s*[45]\b|unreal\s*(?:,|/|&|and|、|和)\s*(?:unity|godot|cocos)", re.I),
    "blender_tool": re.compile(r"blender\s*(?:3d|软件|工具|建模|渲染|动画|render|model|artist)|(?:使用|熟悉|掌握|精通)\s*blender\b|(?:maya|3ds\s*max|houdini|zbrush|cinema\s*4d)\s*(?:,|/|&|and|、|和)\s*blender\b|blender\s*(?:,|/|&|and|、|和)\s*(?:maya|3ds\s*max|houdini|zbrush|cinema\s*4d)", re.I),
    "maya_3d": re.compile(r"maya\s*(?:软件|工具|3d|三维|建模|动画|render|model)|(?:使用|熟悉|掌握|精通)\s*maya\b|maya\s*(?:,|/|&|and|、|和)\s*(?:blender|3ds\s*max|houdini|zbrush)|(?:blender|3ds\s*max|houdini|zbrush)\s*(?:,|/|&|and|、|和)\s*maya", re.I),
    "superset_bi": re.compile(r"apache\s+superset|superset\s*(?:bi|dashboard|数据|可视化|报表|平台|analytics)", re.I),
}
ENGLISH_SKILL_CUE_PREFIX = re.compile(
    r"(?:hands[- ]on(?:\s+experience)?|working knowledge|experience|experienced|proficiency|proficient|"
    r"familiarity|familiar|knowledge|expertise|technical skills|programming skills|skills?|skilled|"
    r"competency|competent)\s+(?:(?:in|with|of|using|on|include|including|such as)\s+)?"
    r"(?:[A-Za-z][A-Za-z0-9.+#-]*\s*(?:(?:,|/|&|and|or)\s+)){0,2}$",
    re.I,
)
ENGLISH_TECH_PAREN_LIST_CUE = re.compile(
    r"(?:hands[- ]on(?:\s+experience)?|working knowledge|experience|experienced|proficiency|proficient|"
    r"familiarity|familiar|knowledge|expertise|technical skills|programming skills|skills?|skilled|"
    r"competency|competent)\s+(?:(?:in|with|of|using|on)\s+)?"
    r"[^.!?;\r\n]{0,160}\b(?:technolog(?:y|ies)|frameworks?|libraries|programming languages?|languages|"
    r"distributed computing|data platforms|cloud platforms|software|tools|systems|services|databases)\b"
    r"[^.!?;\r\n]{0,80}\(\s*(?:(?:e\.g\.|eg|for example|such as|including)\s*)?[^)\r\n]{0,120}$",
    re.I,
)

SPECIAL_ALIAS_GUARDS = {
    ("programming_language", "Go", "Go"): "go_language",
    ("programming_language", "C", "C"): "c_language",
    ("programming_language", "R", "R"): "r_language",
    ("programming_language", "JavaScript", "JS"): "js_acronym",
    ("programming_language", "TypeScript", "TS"): "ts_acronym",
    ("programming_language", "Rust", "Rust"): "rust_language",
    ("programming_language", "Ruby", "Ruby"): "ruby_language",
    ("programming_language", "Swift", "Swift"): "swift_language",
    ("frontend_framework", "React", "React"): "react_framework",
    ("frontend_framework", "Bootstrap CSS", "Bootstrap CSS"): "bootstrap_css",
    ("business_analytics", "SAS Statistical Software", "SAS"): "sas_statistics",
    ("business_analytics", "Apache Superset", "Superset"): "superset_bi",
    ("design_dcc", "Sketch", "Sketch"): "sketch_design",
    ("design_dcc", "Blender", "Blender"): "blender_tool",
    ("design_dcc", "Autodesk Maya", "Maya"): "maya_3d",
    ("game_development", "Unity", "Unity"): "unity_engine",
    ("game_development", "Unreal Engine", "Unreal"): "unreal_engine",
    ("backend_framework", "Flask", "Flask"): "flask_framework",
    ("data_engineering", "Apache Spark", "Spark"): "spark_platform",
    ("data_engineering", "Apache Hive", "Hive"): "hive_platform",
    ("ai_ml_framework", "Ray platform", "Ray"): "ray_platform",
    ("ai_ml_framework", "Triton unresolved mention", "Triton"): "triton_unqualified",
}

TRITON_EXPLICIT_TERM_IDS = {
    "ai_ml_framework_triton_inference_server",
    "ai_ml_framework_triton_language",
}
TRITON_UNRESOLVED_TERM_ID = "ai_ml_framework_triton_unresolved_mention"

LEGACY_GROUP_MAP = {
    "Python": ["Python"], "Java": ["Java"], "C++": ["C++"], "Go": ["Go"], "SQL": ["SQL", "MySQL", "PostgreSQL"],
    "Linux": ["Linux"], "PyTorch": ["PyTorch"], "TensorFlow": ["TensorFlow"], "RAG": ["Retrieval-Augmented Generation"],
    "Agent": ["AI agent", "Multi-agent system"], "Prompt": ["Prompt engineering", "Prompt tuning"],
    "LangChain/LangGraph": ["LangChain", "LangGraph"], "MCP": ["MCP"],
    "工具调用": ["Tool calling", "Function calling"], "评测": ["Benchmarking", "Fine-grained evaluation"],
    "SFT/微调": ["Supervised fine-tuning", "Fine-tuning"],
    "RL/对齐": ["Reinforcement Learning from Human Feedback", "Reinforcement Learning from AI Feedback", "Preference optimization", "Model alignment"],
    "DeepSpeed/Megatron/FSDP": ["DeepSpeed", "Megatron-LM", "Fully Sharded Data Parallel"],
    "CUDA/Triton": ["CUDA", "Triton Inference Server", "Triton language"], "GPU": ["GPU"],
    "vLLM/SGLang/TensorRT": ["vLLM", "SGLang", "TensorRT"],
    "分布式系统": ["MPI", "RDMA", "Kubernetes"], "Kubernetes/Docker": ["Kubernetes", "Docker"],
    "性能优化": ["Inference optimization", "Google Benchmark", "Valgrind"],
    "安全": ["Zero Trust", "Web Application Firewall", "SAST"],
    "数据库/缓存": ["MySQL", "PostgreSQL", "Redis"], "C语言": ["C"],
    "C#/.NET": ["C#", ".NET Core", "ASP.NET Core"], "JavaScript/TypeScript": ["JavaScript", "TypeScript"],
    "React/Vue": ["React", "Vue.js"], "Node.js": ["Node.js"],
    "Android/iOS": ["Android SDK", "iOS SDK", "Kotlin", "Swift"], "Rust": ["Rust"],
    "Spring生态": ["Spring Boot", "Spring Cloud", "Spring Framework", "Spring MVC"],
    "HTTP/RPC/gRPC": ["HTTP", "HTTPS", "gRPC", "REST API"], "微服务": ["Kubernetes", "Istio", "Dubbo"],
    "MySQL/PostgreSQL": ["MySQL", "PostgreSQL"], "Redis": ["Redis"],
    "Elasticsearch/OpenSearch": ["Elasticsearch", "OpenSearch"], "MongoDB": ["MongoDB"],
    "Hadoop/Spark/Flink": ["Apache Hadoop", "Apache Spark", "Apache Flink"],
    "Kafka/MQ": ["Apache Kafka", "Apache Pulsar", "RabbitMQ", "RocketMQ"],
    "ClickHouse": ["ClickHouse"], "Git/CI/CD": ["Git", "GitHub Actions", "GitLab CI/CD", "Jenkins"],
    "AWS/Azure/GCP": ["Amazon Web Services", "Microsoft Azure", "Google Cloud Platform"],
    "NCCL/RDMA": ["NCCL", "RDMA"], "Slurm/Ray": ["Ray Tune"],
    "TVM/MLIR/XLA/LLVM": ["TensorRT", "PyTorch"], "CUTLASS/TileLang": ["CUDA"],
    "CANN/昇腾/MindSpore": ["MindSpore"], "verl/OpenRLHF/Slime": ["TRL"],
    "LlamaFactory/ms-swift": ["Transformers", "Fine-tuning"],
    "量化/蒸馏/剪枝": ["Quantization", "Knowledge distillation", "Pruning"],
    "嵌入式/RTOS": ["Embedded Linux", "FreeRTOS", "Zephyr RTOS"],
    "RTL/Verilog/FPGA": ["Verilog", "SystemVerilog", "FPGA"],
    "SoC/ASIC/RISC-V": ["SoC", "ASIC", "RISC-V"],
    "英语": [],
}

PREFERRED_START = re.compile(
    r"^\s*(?:[•●▪*\-–—]+\s*)?(?:优先(?:条件|要求|项|经验|技能|考虑)?|加分(?:项|条件|经验)?|"
    r"preferred(?:\s+(?:qualifications?|experience|skills?|requirements?))?|"
    r"nice[- ]to[- ]have|bonus(?:\s+(?:qualifications?|experience|skills?))?)\s*[:：]?\s*(.*)$",
    re.I,
)
PREFERRED_END = re.compile(
    r"^\s*(?:[•●▪*\-–—]+\s*)?(?:任职资格|任职要求|岗位要求|基本要求|必备条件|最低条件|"
    r"岗位职责|工作职责|主要职责|职位描述|工作内容|职责|要求|requirements?|qualifications?|"
    r"minimum qualifications?|basic qualifications?|required qualifications?|responsibilities|what you(?:'ll| will) do|about the role|additional information|benefits|what we offer|compensation|equal opportunity|application process|about us|company overview)\s*[:：]?\s*$",
    re.I,
)
ASCII_UPPER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
TOKEN_CANDIDATE_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*(?:[._+#/-][A-Za-z0-9+#]+)*(?![A-Za-z0-9_])")
COMMON_CANDIDATE_STOP = {
    "AI", "API", "APIs", "CEO", "CFO", "CTO", "HR", "QA", "PM", "UI", "UX", "OKR", "KPI",
    "USA", "US", "UK", "EU", "APAC", "EMEA", "ODM", "OEM", "PC", "GPU", "CPU", "SQL", "HTML",
    "HTTP", "HTTPS", "REST", "RPC", "TCP", "UDP", "DNS", "TLS", "SSL", "SLA", "SRE", "CI", "CD",
    "AM", "ID", "JD", "CV", "NDA", "PR", "PO", "IC", "VP", "SVP", "AVP", "NoSQL",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "English", "Chinese",
    "America", "China", "Japan", "Germany", "France", "India", "Europe", "Asia", "Beijing", "Shanghai",
    "NVIDIA", "AMD", "Intel", "Apple", "Google", "Amazon", "Microsoft", "Meta", "ByteDance", "Alibaba",
}


def slug(value: str) -> str:
    normalized = value.lower().replace("#", "sharp").replace("+", "plus")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def builtin_dictionary() -> dict[str, Any]:
    terms = []
    seen_ids: set[str] = set()
    for category, raw in VOCABULARY.items():
        label, term_type = CATEGORY_LABELS[category]
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("|") if part.strip()]
            name, aliases = parts[0], parts[1:]
            term_id = f"{category}_{slug(name)}"
            if term_id in seen_ids:
                raise ValueError(f"duplicate lexicon ID: {term_id}")
            seen_ids.add(term_id)
            all_aliases = list(dict.fromkeys([name, *aliases]))
            guarded = [
                {"alias": alias, "guard": guard}
                for alias in all_aliases
                if (guard := SPECIAL_ALIAS_GUARDS.get((category, name, alias)))
            ]
            term = {
                "id": term_id,
                "name": name,
                "category": category,
                "category_label": label,
                "type": term_type,
                "aliases": all_aliases,
                "guarded_aliases": guarded,
                "case_insensitive": True,
            }
            if name == "Triton unresolved mention":
                term["ambiguity_note"] = "Unqualified Triton mention; do not infer compiler-language or inference-server meaning without context."
                term["semantic_status"] = "unresolved_mention"
            terms.append(term)
    name_to_id = {term["name"]: term["id"] for term in terms}
    legacy_map = {
        legacy: [name_to_id[name] for name in names if name in name_to_id]
        for legacy, names in LEGACY_GROUP_MAP.items()
    }
    return {
        "schema": DICT_SCHEMA,
        "dictionary_version": DICTIONARY_VERSION,
        "snapshot_reference_date": DEFAULT_SNAPSHOT_DATE,
        "created_processing_date": "2026-11-18",
        "scope": "Finite, versioned, atomic technology-name lexicon; a text mention is not a must-have requirement.",
        "category_type_values": {key: {"label": value[0], "type": value[1]} for key, value in CATEGORY_LABELS.items()},
        "terms": terms,
        "legacy_v2_group_mapping": legacy_map,
        "legacy_v2_groups": sorted(LEGACY_GROUP_MAP),
        "matching_policy": {
            "ascii_boundaries": "ASCII identifiers use explicit ASCII word-character lookarounds; Chinese characters adjacent to an English token do not block a match.",
            "short_or_ambiguous_aliases": "Go/C/R/JS/TS, SAS, Sketch, Unity, Blender, Maya, Superset, and selected ordinary-English homonyms require a nearby programming, design, statistical, or product context guard.",
            "substring_policy": "LangChain and LangGraph have separate IDs; Java does not match JavaScript; generic vendor names are not treated as skills.",
        },
        "limitations": [
            "This finite lexicon cannot exhaust natural language, misspellings, local names, new products, or implicit skills.",
            "Matched terms mean only that a string appeared in a source field; they do not establish proficiency, mandatory status, duty ownership, or hiring demand.",
            "Candidate mining is heuristic and candidates are excluded from all technology counts until reviewed and added in a future dictionary version.",
            "The bare token Triton is not assigned automatically: compiler-language and inference-server terms require contextual names; ambiguous mentions remain for review.",
        ],
    }


def read_dictionary(path: Path) -> dict[str, Any]:
    if not path.exists():
        dictionary = builtin_dictionary()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")
        return dictionary
    dictionary = json.loads(path.read_text(encoding="utf-8"))
    if dictionary.get("schema") != DICT_SCHEMA or not isinstance(dictionary.get("terms"), list):
        raise ValueError("dictionary schema is not technology-lexicon/1")
    if not dictionary.get("dictionary_version"):
        raise ValueError("dictionary_version is required")
    ids = [term.get("id") for term in dictionary["terms"]]
    if len(ids) != len(set(ids)):
        raise ValueError("dictionary term IDs must be unique")
    return dictionary


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_identity(dictionary: dict[str, Any], input_path: Path) -> dict[str, str]:
    canonical_dictionary = json.dumps(dictionary, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    extractor_bytes = Path(__file__).resolve().read_bytes()
    return {
        "dictionary_version": dictionary["dictionary_version"],
        "dictionary_sha256": hashlib.sha256(canonical_dictionary).hexdigest(),
        "extractor_version": EXTRACTOR_VERSION,
        "extractor_sha256": hashlib.sha256(extractor_bytes).hexdigest(),
        "parser_version": PARSER_VERSION,
        "source_corpus_sha256": sha256_file(input_path),
    }


class TrieNode:
    __slots__ = ("next", "fail", "outputs")

    def __init__(self) -> None:
        self.next: dict[str, int] = {}
        self.fail = 0
        self.outputs: list[tuple[str, str, str | None]] = []


def make_automaton(dictionary: dict[str, Any]) -> list[TrieNode]:
    nodes = [TrieNode()]
    for term in dictionary["terms"]:
        guards = {item["alias"]: item["guard"] for item in term.get("guarded_aliases", [])}
        for alias in term.get("aliases", []):
            normalized = alias.translate(ASCII_UPPER)
            if not normalized:
                continue
            state = 0
            for char in normalized:
                nxt = nodes[state].next.get(char)
                if nxt is None:
                    nxt = len(nodes)
                    nodes[state].next[char] = nxt
                    nodes.append(TrieNode())
                state = nxt
            output = (term["id"], alias, guards.get(alias))
            if output not in nodes[state].outputs:
                nodes[state].outputs.append(output)
    queue: deque[int] = deque()
    for child in nodes[0].next.values():
        nodes[child].fail = 0
        queue.append(child)
    while queue:
        state = queue.popleft()
        for char, child in nodes[state].next.items():
            queue.append(child)
            fallback = nodes[state].fail
            while fallback and char not in nodes[fallback].next:
                fallback = nodes[fallback].fail
            nodes[child].fail = nodes[fallback].next.get(char, 0)
            nodes[child].outputs.extend(nodes[nodes[child].fail].outputs)
    return nodes


def is_ascii_word(char: str) -> bool:
    return bool(char) and char.isascii() and (char.isalnum() or char == "_")


def has_boundaries(text: str, start: int, end: int, alias: str) -> bool:
    if start > 0 and is_ascii_word(alias[0]) and is_ascii_word(text[start - 1]):
        return False
    if end < len(text):
        after = text[end]
        if alias.casefold() == "c" and after in "+#":
            return False
        if is_ascii_word(alias[-1]) and is_ascii_word(after):
            return False
        if alias[-1] in "+#" and after.isascii() and (after.isalnum() or after in "_+#"):
            return False
    return True


def find_matches(text: str, nodes: list[TrieNode]) -> list[dict[str, Any]]:
    if not text:
        return []
    lowered = text.translate(ASCII_UPPER)
    state = 0
    found: dict[tuple[str, int, int], tuple[str, str | None]] = {}
    for index, char in enumerate(lowered):
        while state and char not in nodes[state].next:
            state = nodes[state].fail
        state = nodes[state].next.get(char, 0)
        for term_id, alias, guard in nodes[state].outputs:
            start, end = index - len(alias) + 1, index + 1
            if start < 0 or not has_boundaries(text, start, end, alias):
                continue
            if guard and guard != "triton_unqualified":
                guarded_phrase_match = any(
                    guard_match.start() <= end and guard_match.end() >= start
                    for guard_match in GUARD_PATTERNS[guard].finditer(text)
                )
                if not guarded_phrase_match:
                    prefix = text[max(0, start - 100):start]
                    guarded_phrase_match = bool(ENGLISH_SKILL_CUE_PREFIX.search(prefix))
                if not guarded_phrase_match:
                    prefix = text[max(0, start - 220):start].replace("e.g.", "eg").replace("E.G.", "EG")
                    guarded_phrase_match = bool(ENGLISH_TECH_PAREN_LIST_CUE.search(prefix))
                if not guarded_phrase_match:
                    continue
            found[(term_id, start, end)] = (alias, guard)
    raw_matches = [
        {"term_id": key[0], "start": key[1], "end": key[2], "alias": value[0], "guard": value[1]}
        for key, value in sorted(found.items(), key=lambda item: (item[0][1], item[0][2], item[0][0]))
    ]
    explicit_triton_matches = [
        match for match in raw_matches if match["term_id"] in TRITON_EXPLICIT_TERM_IDS
    ]
    raw_matches = [
        match for match in raw_matches
        if match["term_id"] != TRITON_UNRESOLVED_TERM_ID
        or not any(
            explicit["start"] < match["end"] and match["start"] < explicit["end"]
            for explicit in explicit_triton_matches
        )
    ]
    selected: list[dict[str, Any]] = []
    by_term: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for match in raw_matches:
        by_term[match["term_id"]].append(match)
    for matches_for_term in by_term.values():
        kept: list[dict[str, Any]] = []
        for match in sorted(matches_for_term, key=lambda item: (item["start"], -(item["end"] - item["start"]))):
            overlapping = [
                old for old in kept
                if match["start"] < old["end"] and old["start"] < match["end"]
            ]
            if any((old["end"] - old["start"]) >= (match["end"] - match["start"]) for old in overlapping):
                continue
            if overlapping:
                kept = [old for old in kept if old not in overlapping]
            kept.append(match)
        selected.extend(kept)
    return sorted(selected, key=lambda item: (item["start"], item["end"], item["term_id"]))


def preferred_segments(text: str) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    active_start: int | None = None
    active_end = 0
    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        match = PREFERRED_START.match(line.strip())
        if match:
            if active_start is not None and active_end > active_start:
                segments.append((active_start, active_end))
            tail = match.group(1)
            if tail.strip():
                active_start = offset + line.find(tail)
                active_end = offset + len(line)
            else:
                active_start = offset + len(line_with_end)
                active_end = active_start
        elif active_start is not None:
            if PREFERRED_END.match(line.strip()):
                if active_end > active_start:
                    segments.append((active_start, active_end))
                active_start = None
                active_end = 0
            else:
                active_end = offset + len(line_with_end)
        offset += len(line_with_end)
    if active_start is not None and active_end > active_start:
        segments.append((active_start, active_end))
    return [(max(0, start), min(len(text), end)) for start, end in segments if end > start]


def ids_in_segments(matches: list[dict[str, Any]], segments: list[tuple[int, int]]) -> set[str]:
    return {
        match["term_id"] for match in matches
        if any(start <= match["start"] and match["end"] <= end for start, end in segments)
    }


def clipped_evidence(text: str, match: dict[str, Any], field: str, job_id: str, preferred: bool = False) -> dict[str, Any]:
    start, end = match["start"], match["end"]
    clip_start, clip_end = max(0, start - 70), min(len(text), end + 90)
    return {
        "job_id": job_id,
        "term_id": match["term_id"],
        "field": field,
        "offset_start": start,
        "offset_end_exclusive": end,
        "matched_alias": match["alias"],
        "snippet_start": clip_start,
        "snippet_end_exclusive": clip_end,
        "snippet": text[clip_start:clip_end],
        "preferred_section": preferred,
    }


def iter_records(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.name.lower()
    if suffix.endswith(".ndjson.gz") or suffix.endswith(".jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError(f"line {line_number} is not a JSON object")
                    yield row
    elif path.suffix.lower() in {".ndjson", ".jsonl"}:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError(f"line {line_number} is not a JSON object")
                    yield row
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("JSON array input expected; use .ndjson or .ndjson.gz for line-oriented input")
        for row in payload:
            if not isinstance(row, dict):
                raise ValueError("all input array members must be JSON objects")
            yield row


def mine_candidate_terms(
    text_fields: list[tuple[str, str]],
    covered_spans: dict[str, list[tuple[int, int]]],
    job_id: str,
    state: dict[str, Any],
) -> None:
    for field, text in text_fields:
        for match in TOKEN_CANDIDATE_RE.finditer(text):
            token = match.group(0)
            if token.upper() in COMMON_CANDIDATE_STOP or len(token) < 3:
                continue
            if any(start <= match.start() and match.end() <= end for start, end in covered_spans.get(field, [])):
                continue
            name_like = (
                bool(re.search(r"[A-Z].*[a-z]|[a-z].*[A-Z]", token))
                or bool(re.search(r"\d|[._+#/-]", token))
                or (token.isupper() and len(token) >= 3)
            )
            common = {
                "requirements", "responsibilities", "experience", "knowledge", "skills", "preferred", "required",
                "ability", "including", "using", "develop", "design", "support", "strong", "excellent", "working",
                "company", "business", "system", "service", "project", "product", "team", "tools", "technology",
                "technical", "solutions", "engineering", "engineer", "software", "hardware", "developing",
                "implement", "implementation", "management", "communication", "customer", "clients", "partner",
                "platform", "application", "applications", "services", "products", "programming", "language",
                "languages", "framework", "frameworks", "responsibility", "responsibilities", "qualification",
                "qualifications", "candidate", "candidates", "professional", "proficiency", "proficient",
                "familiarity", "familiar", "understanding", "hands-on", "hands", "excellent", "good", "work",
            }
            if not name_like or token.casefold() in common:
                continue
            key = token.casefold()
            entry = state.setdefault(key, {"surface_forms": Counter(), "jobs": set(), "fields": Counter(), "examples": []})
            entry["surface_forms"][token] += 1
            entry["jobs"].add(job_id)
            entry["fields"][field] += 1
            if len(entry["examples"]) < 3:
                start, end = match.start(), match.end()
                entry["examples"].append({
                    "job_id": job_id,
                    "field": field,
                    "offset_start": start,
                    "offset_end_exclusive": end,
                    "snippet": text[max(0, start - 55):min(len(text), end + 75)],
                })


def process_row(
    row: dict[str, Any],
    nodes: list[TrieNode],
    dictionary: dict[str, Any],
    canonical_by_id: dict[str, str],
    identity: dict[str, str],
    snapshot_date: str,
    stats: dict[str, Any],
    candidate_state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    job_id = str(row.get("id") or row.get("source_job_id") or "")
    if not job_id:
        raise ValueError("record lacks id and source_job_id")
    req_ok = bool(row.get("requirements_available"))
    req_source_field = "requirements_analysis" if str(row.get("requirements_analysis") or "").strip() else "requirements"
    req_text = str(row.get(req_source_field) or "") if req_ok else ""
    duty_text = str(row.get("description") or "")
    title_text = str(row.get("title") or "")
    full_text = str(row.get("full_text") or "")
    requirement_field = req_source_field if req_ok else "requirements_analysis"
    fields = {
        requirement_field: req_text,
        "description": duty_text,
        "full_text": full_text,
        "title": title_text,
    }
    matched = {field: find_matches(text, nodes) for field, text in fields.items()}
    req_matches = matched[requirement_field] if req_ok else []
    preferred = preferred_segments(req_text) if req_ok else []
    preferred_ids = ids_in_segments(req_matches, preferred)
    req_ids = sorted({item["term_id"] for item in req_matches})
    duty_ids = sorted({item["term_id"] for item in matched["description"]})
    full_ids = sorted({item["term_id"] for item in matched["full_text"]})
    legacy_req = list(row.get("skills_in_requirement") or [])
    legacy_duty = list(row.get("skills_in_responsibility") or [])
    preferred_status = "requirements_unavailable" if not req_ok else ("explicit_section_found" if preferred else "no_explicit_section")
    enrichment = {
        "id": job_id,
        "snapshot_date": snapshot_date,
        **identity,
        "requirements_available": req_ok,
        "requirement_source_field": req_source_field if req_ok else None,
        "technologies_requirement": req_ids,
        "tech_requirement": req_ids,
        "technologies_duty": duty_ids,
        "technologies_preferred": sorted(preferred_ids),
        "preferred_segment_status": preferred_status,
        "technologies_fulltext": full_ids,
        "legacy_skills_in_requirement": legacy_req,
        "legacy_skills_in_duty": legacy_duty,
    }
    index_entry = {
        "requirement": req_ids,
        "duty": duty_ids,
        "fulltext": full_ids,
        "preferred": sorted(preferred_ids),
        "requirements_available": req_ok,
    }
    evidence = []
    for field, text in fields.items():
        if field == requirement_field and not req_ok:
            continue
        by_term: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for match in matched[field]:
            by_term[match["term_id"]].append(match)
        for term_id, term_matches in by_term.items():
            for match in term_matches[:2]:
                is_preferred = field == requirement_field and any(
                    start <= match["start"] and match["end"] <= end for start, end in preferred
                )
                evidence.append({
                    "job_id": job_id,
                    "term_id": term_id,
                    "field": field,
                    "offset_start": match["start"],
                    "offset_end_exclusive": match["end"],
                    "matched_alias": match["alias"],
                    "snippet_start": max(0, match["start"] - 70),
                    "snippet_end_exclusive": min(len(text), match["end"] + 90),
                    "snippet": text[max(0, match["start"] - 70):min(len(text), match["end"] + 90)],
                    "preferred_section": is_preferred,
                    "term_occurrence_count_in_field": len(term_matches),
                })
    covered_spans = {
        field: [(match["start"], match["end"]) for match in matches]
        for field, matches in matched.items()
    }
    candidate_fields = [
        ("title", title_text),
        ("description", duty_text),
        (requirement_field, req_text),
    ]
    mine_candidate_terms(candidate_fields, covered_spans, job_id, candidate_state)
    stats["jobs_seen"] += 1
    stats["requirements_available_jobs"] += int(req_ok)
    stats["requirements_source_nonempty_jobs"] += int(bool(req_text.strip()))
    stats["duty_source_nonempty_jobs"] += int(bool(duty_text.strip()))
    stats["fulltext_nonempty_jobs"] += int(bool(full_text.strip()))
    stats["preferred_explicit_section_jobs"] += int(bool(preferred))
    stats["preferred_unavailable_jobs"] += int(not req_ok)
    stats["record_kinds"][str(row.get("record_kind") or "unknown")] += 1
    stats["title_directions"][str(row.get("title_direction") or "unknown")] += 1
    stats["job_families"][str(row.get("job_family") or "unknown")] += 1
    stats["unique_ids"].add(job_id)
    is_specific = row.get("record_kind") != "分领域毕业生招聘池"
    stats["specific_job_ads_n"] += int(is_specific)
    stats["specific_requirements_available_jobs"] += int(is_specific and req_ok)
    if req_ok:
        for term_id in req_ids:
            stats["term_requirement_jobs"][term_id] += 1
            if is_specific:
                stats["term_requirement_jobs_specific"][term_id] += 1
        canonical_req_ids = {
            match["term_id"] for match in req_matches
            if match["alias"].casefold() == canonical_by_id[match["term_id"]].casefold()
        }
        for term_id in canonical_req_ids:
            stats["term_requirement_canonical_jobs"][term_id] += 1
        for group in legacy_req:
            stats["legacy_group_requirement_jobs"][str(group)] += 1
    for term_id in duty_ids:
        stats["term_duty_jobs"][term_id] += 1
    for term_id in full_ids:
        stats["term_fulltext_jobs"][term_id] += 1
    for term_id in preferred_ids:
        stats["term_preferred_jobs"][term_id] += 1
    return enrichment, index_entry, evidence


def init_stats() -> dict[str, Any]:
    return {
        "jobs_seen": 0,
        "requirements_available_jobs": 0,
        "requirements_source_nonempty_jobs": 0,
        "duty_source_nonempty_jobs": 0,
        "fulltext_nonempty_jobs": 0,
        "preferred_explicit_section_jobs": 0,
        "preferred_unavailable_jobs": 0,
        "specific_job_ads_n": 0,
        "specific_requirements_available_jobs": 0,
        "record_kinds": Counter(),
        "title_directions": Counter(),
        "job_families": Counter(),
        "unique_ids": set(),
        "term_requirement_jobs": Counter(),
        "term_requirement_jobs_specific": Counter(),
        "term_requirement_canonical_jobs": Counter(),
        "term_duty_jobs": Counter(),
        "term_fulltext_jobs": Counter(),
        "term_preferred_jobs": Counter(),
        "legacy_group_requirement_jobs": Counter(),
    }


def alias_collision_report(dictionary: dict[str, Any]) -> list[dict[str, Any]]:
    seen: dict[str, set[str]] = defaultdict(set)
    for term in dictionary["terms"]:
        for alias in term.get("aliases", []):
            seen[alias.translate(ASCII_UPPER)].add(term["id"])
    return [
        {"alias": alias, "term_ids": sorted(ids)}
        for alias, ids in sorted(seen.items()) if len(ids) > 1
    ]


def make_output(
    input_path: Path,
    dictionary_path: Path,
    output_dir: Path,
    analysis_dir: Path,
    snapshot_date: str,
) -> dict[str, Any]:
    dictionary = read_dictionary(dictionary_path)
    identity = artifact_identity(dictionary, input_path)
    nodes = make_automaton(dictionary)
    canonical_by_id = {term["id"]: term["name"] for term in dictionary["terms"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    index_path = data_dir / "technology-index.json"
    enrichment_json = output_dir / "technology_enrichment_v4.json"
    enrichment_gzip = output_dir / "technology_enrichment_v4.json.gz"
    evidence_gzip = output_dir / "technology_evidence_v4.ndjson.gz"
    dictionary_copy = data_dir / "technology_dictionary_v4.json"
    dictionary_copy.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the exact frozen dictionary in the requested analysis folder as well.
    analysis_dictionary = analysis_dir / "technology_dictionary_v4.json"
    if analysis_dictionary.resolve() != dictionary_path.resolve():
        analysis_dictionary.write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = init_stats()
    candidate_state: dict[str, Any] = {}
    jobs_index: dict[str, Any] = {}
    with (
        enrichment_json.open("w", encoding="utf-8") as plain,
        gzip.open(enrichment_gzip, "wt", encoding="utf-8") as zipped,
        gzip.open(evidence_gzip, "wt", encoding="utf-8") as evidence_stream,
    ):
        header = {
            "schema": "technology-enrichment/1",
            "snapshot_date": snapshot_date,
            **identity,
        }
        header_text = json.dumps(header, ensure_ascii=False, separators=(",", ":"))[:-1] + ',"jobs":['
        for stream in (plain, zipped):
            stream.write(header_text)
        first = True
        for row in iter_records(input_path):
            enrichment, index_entry, evidence = process_row(
                row, nodes, dictionary, canonical_by_id, identity, snapshot_date, stats, candidate_state
            )
            job_id = enrichment["id"]
            if job_id in jobs_index:
                raise ValueError(f"duplicate job id {job_id}")
            if not enrichment["requirements_available"] and enrichment["technologies_requirement"]:
                raise AssertionError(f"unavailable qualification terms must be empty: {job_id}")
            jobs_index[job_id] = index_entry
            if not first:
                plain.write(",")
                zipped.write(",")
            encoded = json.dumps(enrichment, ensure_ascii=False, separators=(",", ":"))
            plain.write(encoded)
            zipped.write(encoded)
            first = False
            if evidence:
                evidence_stream.write(json.dumps({
                    "job_id": job_id,
                    "snapshot_date": snapshot_date,
                    **identity,
                    "evidence": evidence,
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
        plain.write("]}")
        zipped.write("]}")

    terms_for_index = [
        {
            **{key: term[key] for key in ("id", "name", "category", "aliases", "type")},
            **({"ambiguity_note": term["ambiguity_note"]} if term.get("ambiguity_note") else {}),
            **({"semantic_status": term["semantic_status"]} if term.get("semantic_status") else {}),
        }
        for term in dictionary["terms"]
    ]
    index_doc = {
        **identity,
        "snapshot_date": snapshot_date,
        "terms": terms_for_index,
        "jobs": jobs_index,
    }
    index_path.write_text(json.dumps(index_doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    candidate_items = []
    for key, entry in candidate_state.items():
        if len(entry["jobs"]) < 2:
            continue
        form = entry["surface_forms"].most_common(1)[0][0]
        candidate_items.append({
            "candidate": form,
            "normalized": key,
            "document_frequency": len(entry["jobs"]),
            "field_mentions": dict(entry["fields"].most_common()),
            "surface_forms": [
                {"value": value, "occurrences": n} for value, n in entry["surface_forms"].most_common(5)
            ],
            "examples": entry["examples"],
            "status": "review_pending",
            "counted_as_technology_demand": False,
        })
    candidate_items.sort(key=lambda item: (-item["document_frequency"], item["candidate"].casefold()))
    candidate_cap = 2000
    candidate_items = candidate_items[:candidate_cap]
    candidates_path = analysis_dir / "technology_candidates_v4.json"
    candidates_path.write_text(json.dumps({
        "schema": "technology-candidates/1",
        "snapshot_date": snapshot_date,
        **identity,
        "method": "Heuristic surface-form discovery (CamelCase, acronyms, digits, punctuation-bearing identifiers); minimum two distinct job IDs; lexicon-covered spans are excluded. Candidate status is review_pending; candidates are never included in technology counts.",
        "candidate_count_after_threshold_and_cap": len(candidate_items),
        "max_candidates": candidate_cap,
        "candidates": candidate_items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    eligible_n = stats["requirements_available_jobs"]
    specific_eligible_n = stats["specific_requirements_available_jobs"]
    duty_n = stats["duty_source_nonempty_jobs"]
    full_n = stats["fulltext_nonempty_jobs"]
    categories = {
        category: sum(term["category"] == category for term in dictionary["terms"])
        for category in CATEGORY_LABELS
    }
    term_stats = []
    for term in dictionary["terms"]:
        term_id = term["id"]
        requirement_n = stats["term_requirement_jobs"][term_id]
        canonical_n = stats["term_requirement_canonical_jobs"][term_id]
        duty_count = stats["term_duty_jobs"][term_id]
        full_count = stats["term_fulltext_jobs"][term_id]
        preferred_count = stats["term_preferred_jobs"][term_id]
        term_stats.append({
            "id": term_id,
            "name": term["name"],
            "category": term["category"],
            "type": term["type"],
            "requirement_n": requirement_n,
            "requirement_denominator_n": eligible_n,
            "requirement_pct": round(100 * requirement_n / eligible_n, 4) if eligible_n else None,
            "requirement_specific_n": stats["term_requirement_jobs_specific"][term_id],
            "requirement_specific_denominator_n": specific_eligible_n,
            "requirement_canonical_name_n": canonical_n,
            "duty_n": duty_count,
            "duty_denominator_n": duty_n,
            "duty_pct": round(100 * duty_count / duty_n, 4) if duty_n else None,
            "fulltext_n": full_count,
            "fulltext_denominator_n": full_n,
            "fulltext_pct": round(100 * full_count / full_n, 4) if full_n else None,
            "preferred_n": preferred_count,
            "preferred_denominator_n": stats["preferred_explicit_section_jobs"],
        })
    term_stats.sort(key=lambda item: (-item["requirement_n"], item["name"].casefold()))

    collisions = alias_collision_report(dictionary)
    term_ids = {term["id"] for term in dictionary["terms"]}
    langchain_id = next((term["id"] for term in dictionary["terms"] if term["name"] == "LangChain"), None)
    langgraph_id = next((term["id"] for term in dictionary["terms"] if term["name"] == "LangGraph"), None)
    pools_n = stats["record_kinds"].get("分领域毕业生招聘池", 0)
    stats_doc = {
        "schema": "technology-stats/1",
        "snapshot_date": snapshot_date,
        "processing_date": date.today().isoformat(),
        **identity,
        "input_file": input_path.name,
        "record_count": stats["jobs_seen"],
        "unique_job_ids_n": len(stats["unique_ids"]),
        "specific_job_ads_n": stats["specific_job_ads_n"],
        "aggregated_graduate_pools_n": pools_n,
        "requirements_available_n": eligible_n,
        "specific_requirements_available_n": specific_eligible_n,
        "requirements_text_nonempty_n": stats["requirements_source_nonempty_jobs"],
        "requirements_denominator_definition": "All input records with requirements_available=true are in the all-record denominator. Requirement terms are searched in requirements_analysis, falling back to requirements only when analysis is empty. False-flag records receive empty requirement arrays and are excluded from qualification counts.",
        "specific_ad_denominator_definition": "Specific job ads exclude record_kind=分领域毕业生招聘池; both all-record and specific-ad qualification denominators are exported so downstream controls can reproduce either scope.",
        "duty_denominator_n": duty_n,
        "fulltext_denominator_n": full_n,
        "preferred_explicit_sections_n": stats["preferred_explicit_section_jobs"],
        "preferred_denominator_definition": "Jobs with requirements_available=true and an explicitly headed preferred/bonus section detected; this is not the full requirement denominator.",
        "counts_are_job_presence": True,
        "record_kinds": dict(stats["record_kinds"].most_common()),
        "title_directions": dict(stats["title_directions"].most_common()),
        "job_families": dict(stats["job_families"].most_common()),
        "category_term_counts": categories,
        "term_stats_sorted_by_requirement_n": term_stats,
        "legacy_v2_group_requirement_counts": dict(stats["legacy_group_requirement_jobs"].most_common()),
        "candidate_review_queue": {
            "candidate_count_emitted": len(candidate_items),
            "minimum_document_frequency": 2,
            "candidates_counted_as_demand": 0,
            "review_file": candidates_path.name,
        },
        "quality_checks": {
            "terms_n": len(dictionary["terms"]),
            "expected_at_least_300_terms": len(dictionary["terms"]) >= 300,
            "unique_ids_n": len(term_ids),
            "duplicate_ids_n": len(dictionary["terms"]) - len(term_ids),
            "duplicate_exact_aliases_across_terms": collisions,
            "separate_langchain_langgraph_ids": bool(langchain_id and langgraph_id and langchain_id != langgraph_id),
            "nvidia_brand_is_not_a_term": not any(term["name"].casefold() == "nvidia" for term in dictionary["terms"]),
            "requirements_false_rows_have_empty_requirement_terms": True,
            "no_raw_fulltext_copied_to_enrichment": True,
            "offset_convention": "Python Unicode code-point indexes; start inclusive, end exclusive, relative to the exact field string.",
            "source_snapshot_vs_processing_date": {
                "snapshot_date": snapshot_date,
                "processing_date": date.today().isoformat(),
                "interpretation": "Processing date does not imply a new job-market collection.",
            },
        },
    }
    stats_path = analysis_dir / "technology_stats_v4.json"
    stats_path.write_text(json.dumps(stats_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "dictionary": dictionary,
        "stats": stats_doc,
        "candidates": candidate_items,
        "paths": {
            "dictionary": str(analysis_dictionary),
            "index": str(index_path),
            "enrichment": str(enrichment_json),
            "enrichment_gzip": str(enrichment_gzip),
            "evidence_gzip": str(evidence_gzip),
            "stats": str(stats_path),
            "candidates": str(candidates_path),
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    dictionary, stats = result["dictionary"], result["stats"]
    terms = stats["term_stats_sorted_by_requirement_n"]
    top = [item for item in terms if item["requirement_n"]][:35]
    checks = stats["quality_checks"]
    lines = [
        "# 技术词典与岗位技术证据 v4",
        "",
        f"快照日期：{stats['snapshot_date']}。处理日期：{stats['processing_date']}。处理日期是本地运算时间，不代表重新采集市场数据。",
        f"词典版本：{dictionary['dictionary_version']}；原子词项 {len(dictionary['terms']):,} 个，覆盖 {len(stats['category_term_counts'])} 个领域。",
        f"规则身份：dictionary_sha256={stats['dictionary_sha256']}；extractor_version={stats['extractor_version']}；extractor_sha256={stats['extractor_sha256']}；parser_version={stats['parser_version']}；source_corpus_sha256={stats['source_corpus_sha256']}。语料哈希绑定当前输入文件字节；跨快照变化属正常，不要求相同。",
        "",
        "## 数据与分母",
        "",
        f"本次处理 {stats['record_count']:,} 条记录、去重岗位ID {stats['unique_job_ids_n']:,} 条；其中具体职位 {stats['specific_job_ads_n']:,} 条，聚合毕业生招聘池 {stats['aggregated_graduate_pools_n']:,} 条。",
        f"资格分析使用 requirements_available=true 的 {stats['requirements_available_n']:,} 条作全记录分母；只看具体职位时分母为 {stats['specific_requirements_available_n']:,} 条。词项计数为有该词项的岗位数，不是字符串出现次数。",
        f"职责文本分母为 description 非空的 {stats['duty_denominator_n']:,} 条；全文分母为 full_text 非空的 {stats['fulltext_denominator_n']:,} 条。职责、资格和全文分开统计，同一岗位可以在多个字段命中。",
        f"显式优先/加分分段检测到 {stats['preferred_explicit_sections_n']:,} 条；technologies_preferred 只从明确标题分段提取。零值或空字段不代表该技能不重要。",
        "",
        "## 词典与接口",
        "",
        f"词典固定版本为 {dictionary['dictionary_version']}。每项含稳定ID、规范名、领域category、类型type和别名aliases；LangChain与LangGraph使用独立ID。type区分language、framework、concept、platform_product、hardware、protocol和tool。既有v2分组词项通过legacy_skills_in_requirement与legacy_skills_in_duty原样保留。",
        "NVIDIA作为厂商名不单独算技术项；具体的CUDA、TensorRT、Triton Inference Server等名称可分别计数。Triton编译语言与推理服务器分为两个原子项，裸Triton不自动归入任一项。",
        "另有Triton unresolved mention，专门保留无法从近邻上下文分辨的裸Triton；当Triton language或Triton Inference Server上下文明确时，该项不会重复命中。",
        "接口索引位于 data/technology-index.json，顶层含dictionary_version、snapshot_date、terms与jobs。每个jobs[id]包含requirement、duty、fulltext、preferred四组ID及requirements_available。逐岗enrichment同时含technologies_requirement与兼容字段tech_requirement。",
        "evidence/technology_evidence_v4.ndjson.gz按岗位保存命中字段、匹配别名、证据片段和偏移。offset以原字段Python Unicode字符索引计，start包含、end不包含。enrichment不复制岗位全文。",
        "",
        "## 资格文本提及较多的原子项",
        "",
        "| 技术项 | 类型 | 领域 | 提及岗位 n/资格分母 | 提及率 | 职责 n/分母 | 全文 n/分母 |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for item in top:
        lines.append(
            f"| {item['name']} | {item['type']} | {item['category']} | "
            f"{item['requirement_n']:,}/{item['requirement_denominator_n']:,} | {item['requirement_pct']:.2f}% | "
            f"{item['duty_n']:,}/{item['duty_denominator_n']:,} | {item['fulltext_n']:,}/{item['fulltext_denominator_n']:,} |"
        )
    lines += [
        "",
        "只要词面出现就计为提及；这不判断技能是必备、优先、任选、替代项还是仅作为上下文。需要按原文证据进一步读逻辑。",
        "",
        "## 领域覆盖",
        "",
        "| 领域 | 词项数 |",
        "|---|---:|",
    ]
    for category, count in stats["category_term_counts"].items():
        label = dictionary["category_type_values"].get(category, {}).get("label", category)
        lines.append(f"| {label} ({category}) | {count} |")
    lines += [
        "",
        "## 自动质检",
        "",
        f"词项数≥300：{checks['expected_at_least_300_terms']}；重复ID：{checks['duplicate_ids_n']}；LangChain/LangGraph独立ID：{checks['separate_langchain_langgraph_ids']}；NVIDIA厂商名单独不作为技术项：{checks['nvidia_brand_is_not_a_term']}；资格不可用岗位资格数组为空：{checks['requirements_false_rows_have_empty_requirement_terms']}；enrichment未复制全文：{checks['no_raw_fulltext_copied_to_enrichment']}。",
        f"完全相同的别名跨ID冲突 {len(checks['duplicate_exact_aliases_across_terms'])} 组，见technology_stats_v4.json。冲突项会以不同ID并行保留，使用时需结合片段复核。",
        "",
        "## 候选词审阅队列",
        "",
        f"启发式从标题、职责、资格文本挖掘出 {stats['candidate_review_queue']['candidate_count_emitted']:,} 个至少出现在2个岗位的未收录英文/混合候选，最多保留2,000项；每项带字段、偏移和片段例证。候选不计入技术提及统计，待人工复核后才能进入后续词典版本。",
        "规则偏向CamelCase、缩写、数字和标点形式，可能漏掉全小写新名称，也可能含人名、品牌或普通词；这不是自然语言穷尽式术语发现。",
        "",
        "## 优先项与资格逻辑",
        "",
        "只有“Preferred qualifications”“优先条件”“加分项”等显式标题分段才填technologies_preferred。单独出现“熟悉”“优先”等字眼不用于推断偏好。technologies_requirement只表示资格字段里出现该词，不自动等于硬性门槛。空缺未拆为明确优先段时，preferred_segment_status会给出no_explicit_section或requirements_unavailable。",
        "",
        "## 后续时间比较",
        "",
        f"快照固定为 {stats['snapshot_date']}；处理日期仅记录离线处理发生时间。以后用同一词典版本 {dictionary['dictionary_version']} 重跑新快照并填真实采集日期，才能比较同口径变化。审定新候选后应发布新dictionary_version，并对历史快照同时重算或单独标注词典断点。",
        "词典是有限版本，不能覆盖所有自然语言、拼写变体、隐含技能或不断出现的新技术。技术提及不代表技能熟练度、岗位主责、全国需求、HC或录用概率。",
        "",
        "## 文件",
        "",
        "- analysis/technology_dictionary_v4.json：冻结词典、别名、分类和legacy映射。",
        "- analysis/technology_stats_v4.json：分母、职位加权提及数、类型/类别和质量检查。",
        "- analysis/technology_candidates_v4.json：未收录候选词人工复核队列。",
        "- analysis/technology_coverage_v4.md：本说明与汇总。",
        "- evidence/technology_v4/data/technology-index.json：适配接口索引。",
        "- evidence/technology_v4/technology_enrichment_v4.json及.json.gz：紧凑逐岗词项列表。",
        "- evidence/technology_v4/technology_evidence_v4.ndjson.gz：逐岗原文字段证据片段与偏移。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract versioned atomic technology mentions from a local job snapshot.")
    parser.add_argument("--input", required=True, type=Path, help="JSON array, NDJSON, or NDJSON.GZ snapshot.")
    parser.add_argument("--dictionary", required=True, type=Path, help="Frozen lexicon JSON; if absent, bootstrap the built-in v4 dictionary at this path.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Folder for evidence enrichment and data/technology-index.json.")
    parser.add_argument("--analysis-dir", type=Path, default=Path(__file__).resolve().parent, help="Folder for dictionary, statistics, candidate queue, and Markdown report.")
    parser.add_argument("--snapshot-date", default=DEFAULT_SNAPSHOT_DATE, help="Source snapshot date; defaults to 2026-11-17 and is distinct from processing date.")
    args = parser.parse_args()
    if not args.input.exists():
        parser.error(f"input does not exist: {args.input}")
    result = make_output(args.input, args.dictionary, args.output_dir, args.analysis_dir, args.snapshot_date)
    coverage_path = args.analysis_dir / "technology_coverage_v4.md"
    coverage_path.write_text(render_markdown(result), encoding="utf-8")
    result["paths"]["coverage"] = str(coverage_path)
    print(json.dumps({
        "paths": result["paths"],
        "records": result["stats"]["record_count"],
        "specific_job_ads": result["stats"]["specific_job_ads_n"],
        "requirements_available": result["stats"]["requirements_available_n"],
        "specific_requirements_available": result["stats"]["specific_requirements_available_n"],
        "terms": len(result["dictionary"]["terms"]),
        "candidates": result["stats"]["candidate_review_queue"]["candidate_count_emitted"],
        "dictionary_version": result["dictionary"]["dictionary_version"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()




