# The Property Developer's Guide to Sandboxing & Infrastructure Engineering

> **Career Trajectory**: Building Inspector (Infrastructure Engineer) → Licensed Architect (Systems Software Engineer)
>
> You're not just learning to manage properties — you're learning to build them from the ground up, pour the foundation, wire the electrical, and eventually design entire developments that house thousands of tenants securely.

---

## Table of Contents

1. [The Glossary: Real Estate ↔ Systems](#the-glossary-real-estate--systems)
2. [Property Survey: Skills Extracted from JDs](#property-survey-skills-extracted-from-jds)
3. [Phase 1 — The Building Inspector: Infrastructure Engineer, Sandboxing](#phase-1--the-building-inspector-infrastructure-engineer-sandboxing)
4. [Phase 2 — The Licensed Architect: Software Engineer, Sandboxing (Systems)](#phase-2--the-licensed-architect-software-engineer-sandboxing-systems)
5. [The Curriculum: MIT Course Roadmap](#the-curriculum-mit-course-roadmap)
6. [The Construction Plan: Projects Roadmap](#the-construction-plan-projects-roadmap)
7. [The Inspection Checklist: Milestones & Verification](#the-inspection-checklist-milestones--verification)
8. [Resources & References](#resources--references)

---

## The Glossary: Real Estate ↔ Systems

Before we break ground, learn the language. Every technical concept in this guide maps to something you already understand from real estate.

| Technical Concept | Real Estate Analogy | Why It Clicks |
|---|---|---|
| **Kernel** | The **land/soil** everything is built on | You can't build anything without it. It's the raw earth — manages who gets to build what, where, and when. Every structure (process) sits on this land. |
| **Hypervisor (KVM)** | The **concrete foundation/slab** | Poured on top of the land. It's what lets you build multiple independent structures (VMs) on the same plot. Without it, one building per lot. |
| **Virtual Machine (VM)** | A **standalone house** with its own foundation | Complete isolation. Own plumbing, electrical, HVAC. Expensive to build but nobody shares walls. Your neighbor's kitchen fire doesn't touch you. |
| **Container (Docker)** | An **apartment unit** in a shared building | Shares the building's foundation, plumbing, and electrical (kernel) but has its own locked front door. Cheaper and faster to build than a house, but the walls are thinner. |
| **microVM (Firecracker)** | A **prefab modular home** | Factory-built in 125ms, dropped onto a lot, self-contained like a house but at apartment cost. This is what AWS Lambda and Anthropic use — the best of both worlds. |
| **Namespace isolation** | **Property lines & zoning boundaries** | Your property line defines what you can see and access. A process in its own namespace can't see its neighbor's yard, garage, or mailbox. |
| **cgroups** | **HOA resource limits** | The HOA says: "You get 2 parking spots (CPU cores), 1500 sqft (memory), and your water bill is capped (I/O bandwidth)." Prevents one tenant from hogging the pool. |
| **seccomp** | **Building code enforcement** | The city inspector's rulebook. Says what system calls (construction methods) are allowed. "No, you can't install a gas line in a wood-frame building." Blocks dangerous operations at the kernel level. |
| **Kubernetes (K8s)** | **Property management company** | Manages hundreds of buildings (nodes) across multiple neighborhoods (clusters). Handles tenant placement, evictions (pod scheduling), maintenance (self-healing), and scaling (adding units). |
| **Distributed systems** | **Real estate portfolio across multiple cities** | Properties in SF, NYC, and Seattle. They need to stay in sync (consistency), survive a hurricane in one city (fault tolerance), and keep operating even when communication is slow (partition tolerance). That's the CAP theorem of real estate. |
| **Kernel modules** | **Utility hookups** (plumbing, electrical, gas) | Pluggable infrastructure added to the land. Need fiber internet? Load the network module. Need GPU access? Load the driver module. Hot-swappable without demolishing the building. |
| **Infrastructure as Code (Terraform)** | **Architectural blueprints** | Reproducible construction documents. Hand the blueprint to any contractor (cloud provider), they build the same building every time. Version-controlled, peer-reviewed, auditable. |
| **Observability (monitoring/alerting)** | **Security cameras, smoke detectors, property inspections** | You can't manage what you can't see. Metrics = utility meters. Logs = maintenance records. Traces = following a plumber through every room they touched on a service call. |
| **Multi-tenant systems** | **Mixed-use building** | Ground floor is retail (public API), floors 2-10 are residential (user workloads), penthouse is admin. Everyone shares the elevator (network) but can't access each other's units. |
| **Serverless (Lambda/Cloud Run)** | **Airbnb / short-term rental** | You don't own the building, don't manage it, don't maintain it. You just rent execution time. Someone else handles the plumbing. You pay per night (per invocation), not per month. |
| **Context switch** | **Showing different tenants the same model unit** | The leasing agent (CPU) can only show one family at a time. Switching between families takes time (overhead) — you have to reset the model unit, pull up new paperwork, adjust the presentation. |
| **Virtual memory** | **Square footage allocation** | Every tenant thinks they have 10,000 sqft (virtual address space), but the building only has 50,000 sqft total (physical RAM). The property manager uses a floorplan map (page table) to translate "my living room" into actual physical space. Some "rooms" might actually be in off-site storage (swap/disk). |
| **Page table** | **The master floorplan** | Maps every tenant's room number to an actual physical location in the building. When you say "go to my bedroom," the floorplan tells you it's Room 4B on the 3rd floor. |
| **I/O scheduler** | **Elevator scheduling in a high-rise** | 50 people want the elevator at 8am. Who goes first? The scheduler optimizes for throughput (most people moved) vs. latency (no one waits too long) vs. fairness (penthouse doesn't always get priority). |
| **System calls** | **Submitting a work order to building management** | Tenants (user programs) can't fix their own plumbing — they submit a work order (syscall) to the building manager (kernel), who does the privileged work and reports back. |
| **Load balancer** | **Gated community with multiple entrances** | Traffic cop at the gate. Distributes incoming cars (requests) across multiple driveways (servers) so no single entrance gets gridlocked. |
| **Circuit breaker** | **Emergency shutoff valve** | When a pipe bursts (downstream service fails), the shutoff valve (circuit breaker) cuts flow to prevent flooding the whole building. After repairs, you cautiously turn it back on (half-open state). |
| **Bubblewrap (bwrap)** | **Construction site fencing** | Temporary, lightweight perimeter control. Cheaper than building a permanent wall (full VM). Used by Anthropic's sandbox-runtime on Linux to fence off processes. |
| **Seatbelt (macOS sandbox)** | **Gated community security profile** | A written security policy that says what residents (processes) can and can't do. "No loud parties (network access) after 10pm unless you're on the approved list." |

---

## Property Survey: Skills Extracted from JDs

### Phase 1: Infrastructure Engineer, Sandboxing

> **The Building Inspector** — You manage, scale, and secure existing properties. You don't pour the foundation yourself, but you know exactly what good construction looks like and you operate the buildings at scale.

**Source**: [Anthropic — Infrastructure Engineer, Sandboxing](https://job-boards.greenhouse.io/anthropic/jobs/5030680008)

**The Role**: Build and scale systems that enable researchers to safely execute AI-generated code in isolated environments. Distributed systems that operate reliably at significant scale while maintaining strong security boundaries.

#### Required Skills (The Must-Haves for Your License)

| Skill | Real Estate Translation | Proficiency Target |
|---|---|---|
| **5+ years backend infrastructure at scale** | 5+ years managing large commercial properties | Senior-level operational experience |
| **Distributed systems design & implementation** | Managing a multi-city property portfolio | Design systems that survive datacenter failures |
| **Strong operational experience / debugging production** | Emergency maintenance & crisis management | Root-cause a 3am outage in a distributed system |
| **Cloud platforms (GCP primary; AWS/Azure valuable)** | Knowing your way around the county recorder's office, zoning board, permit office | GCP-first, but polyglot cloud literacy |
| **Containerization (Docker, Kubernetes)** | Building and managing apartment complexes | Deploy, scale, debug containerized workloads |
| **Container security implications** | Fire code, structural integrity inspections | Understand escape vectors, privilege escalation |
| **Infrastructure as Code / DevOps practices** | Architectural blueprints & reproducible builds | Terraform/Pulumi, CI/CD pipelines, GitOps |
| **Programming: Python, Go, or Rust** | The tools of the trade (hammer, level, tape measure) | Production-quality code in at least one |

#### Nice-to-Have Skills (The Luxury Upgrades)

| Skill | Real Estate Translation | Why It Matters |
|---|---|---|
| **Serverless (Cloud Functions, Cloud Run, Lambda)** | Airbnb property management | Anthropic likely uses serverless for sandbox execution |
| **Secure multi-tenant system design** | Mixed-use building security architecture | Core to sandboxing — isolating untrusted AI code |
| **HPC / ML infrastructure** | Managing a data center campus | Context for *why* these sandboxes exist |
| **Linux internals: namespaces, cgroups, seccomp** | Building code, property lines, HOA rules | The actual isolation primitives you'll operate |

#### Responsibilities Breakdown

1. **Design, build, operate distributed backend systems** for sandboxed execution → You're the general contractor and property manager for the entire sandbox development
2. **Scale infrastructure** while maintaining reliability/performance → Adding floors to a skyscraper while tenants are living in it
3. **Implement serverless architectures & container orchestration** → Building the Airbnb platform for code execution
4. **Collaborate with research teams** → Talking to the tenants to understand what they need from the building
5. **Develop monitoring, alerting, observability** → Installing security cameras, smoke detectors, and utility meters across every property
6. **On-call rotations** → You're the emergency maintenance number on the fridge
7. **Infrastructure automation & tooling** → Building the blueprint-to-building pipeline
8. **Partner with security teams** → Working with the fire marshal to ensure code compliance

---

### Phase 2: Software Engineer, Sandboxing (Systems)

> **The Licensed Architect** — You don't just manage buildings; you design the structural systems themselves. You understand soil composition (kernel internals), can specify custom foundation types (hypervisors), and optimize the building's core systems (virtualization stack) for maximum efficiency.

**Source**: [Anthropic — Software Engineer, Sandboxing (Systems)](https://job-boards.greenhouse.io/anthropic/jobs/5025591008)

**The Role**: Linux OS and System Programming Subject Matter Expert. Accelerate and optimize virtualization and VM workloads powering AI infrastructure. Low-level system programming, kernel optimization, and virtualization technologies.

#### Required Skills (Architect's License Requirements)

| Skill | Real Estate Translation | Proficiency Target |
|---|---|---|
| **Linux kernel development** | Understanding soil composition, geology, and land grading | Write kernel modules, patch the kernel, understand the source |
| **System programming / low-level software engineering** | Structural engineering — load calculations, foundation design | Comfortable in the kernel, not just userspace |
| **Virtualization (KVM, Xen, QEMU)** | Foundation systems — slab-on-grade, pier-and-beam, deep foundations | Understand how VMs are created, scheduled, and optimized |
| **System performance optimization for compute-intensive workloads** | Energy efficiency retrofitting for industrial buildings | Profile, benchmark, and optimize at the system level |
| **CPU architectures & memory systems** | Understanding the raw materials — steel grades, concrete PSI, lumber specs | x86_64, ARM64, NUMA, cache hierarchies, TLBs |
| **C/C++ programming** | Masonry and steel fabrication — the foundational building materials | Production-quality systems code |
| **Rust (ideally)** | Modern engineered lumber (CLT) — stronger, safer, newer | Memory-safe systems programming |

#### Example Projects from the JD (The Architect's Portfolio)

These are actual projects Anthropic listed — they tell you exactly what you'd build:

| Project | Real Estate Translation | What You'd Learn |
|---|---|---|
| **Optimize kernel params & VM configs to reduce LLM inference latency** | Tuning HVAC systems for optimal airflow in a server room building | Kernel tuning, VM performance profiling |
| **Custom memory management for large-scale distributed training** | Designing a custom water distribution system for a 50-story building | Memory allocators, NUMA-aware allocation, huge pages |
| **Specialized I/O schedulers for ML workloads** | Building a custom elevator system optimized for freight (GPU data) | Linux block layer, scheduler algorithms, BPF |
| **Lightweight virtualization for AI inference** | Designing prefab modular homes (microVMs) for rapid deployment | Firecracker, Cloud Hypervisor, minimal VM design |
| **Monitoring & instrumentation for system-level bottlenecks** | Installing smart building sensors for predictive maintenance | perf, eBPF, ftrace, custom metrics |
| **Enhancing inter-VM communication for distributed training** | Building skywalks between buildings for faster tenant movement | virtio, vhost, shared memory, DPDK |

---

### Skills Delta: Inspector → Architect

What changes between Phase 1 and Phase 2:

| Dimension | Phase 1 (Inspector) | Phase 2 (Architect) |
|---|---|---|
| **Abstraction level** | Operates above the kernel (containers, K8s, cloud APIs) | Operates inside and below the kernel (modules, hypervisors, hardware) |
| **Primary languages** | Python, Go, Rust | C, C++, Rust |
| **Core domain** | Distributed systems, cloud infrastructure, orchestration | OS internals, virtualization, hardware-software interface |
| **What you optimize** | Availability, scalability, cost | Latency, throughput, resource efficiency at the microsecond level |
| **Security focus** | Container isolation, network policies, IAM | Kernel-level isolation, hypervisor security, syscall filtering |
| **Mental model** | "How do I manage 10,000 apartments across 50 buildings?" | "How do I make each apartment's walls thinner without losing soundproofing?" |

---

## The Curriculum: MIT Course Roadmap

These three MIT courses are your formal education. Think of them as getting your **engineering degree** before you start building.

### Recommended Sequence

```
Semester 1 (Months 1-4)          Semester 2 (Months 5-8)          Semester 3 (Months 9-12)
┌─────────────────────┐          ┌─────────────────────┐          ┌─────────────────────┐
│   MIT 6.1810        │          │   MIT 6.5840        │          │   MIT 6.172         │
│   OS Engineering    │    →     │   Distributed       │    →     │   Performance       │
│                     │          │   Systems           │          │   Engineering       │
│   "Land surveying   │          │   "Multi-city       │          │   "Structural       │
│    & soil science"  │          │    portfolio mgmt"  │          │    optimization"    │
└─────────────────────┘          └─────────────────────┘          └─────────────────────┘
    Maps to: Phase 2                 Maps to: Phase 1                Maps to: Phase 2
    (Kernel, VM, memory)             (Distributed, fault tol.)       (Perf, C, caching)
```

> **Why this order?** You need to understand how a single building works (OS) before managing a portfolio (distributed), and you need both before optimizing structures for peak performance.

---

### Course 1: MIT 6.1810 — Operating System Engineering

> **Real Estate Equivalent**: Land Surveying & Soil Science — Understanding the ground everything is built on

**Course URL**: https://pdos.csail.mit.edu/6.828/ | [MIT OCW (Fall 2023)](https://ocw.mit.edu/courses/6-1810-operating-system-engineering-fall-2023/)

**Textbook**: *xv6: A Simple, Unix-Like Teaching Operating System* — Russ Cox, Frans Kaashoek, Robert Morris

**What You'll Learn** (mapped to JD skills):

| Lab / Topic | Real Estate Analogy | JD Skill It Builds |
|---|---|---|
| **xv6 boot process** | Breaking ground — how a building goes from empty lot to occupiable | System initialization, hardware bootstrapping |
| **System calls** | The work order system between tenants and building management | Kernel-userspace boundary, syscall interface |
| **Page tables & virtual memory** | The master floorplan — mapping tenant rooms to physical space | Virtual memory (critical for VM optimization in Phase 2) |
| **Traps & interrupts** | Fire alarms and emergency protocols — handling unexpected events | Exception handling, interrupt controllers |
| **Process scheduling** | Tenant time-sharing for shared amenities (laundry room, gym) | CPU scheduling algorithms, context switches |
| **File systems** | The storage unit facility — how belongings are organized and retrieved | Block layer, inode structures, journaling |
| **Concurrency & locks** | Key management — making sure two maintenance crews don't work the same unit simultaneously | Mutexes, spinlocks, deadlock prevention |
| **Networking** | The mailroom and intercom system | Network stack, sockets, protocols |

**How to Study**:
1. Watch the lecture videos (available on YouTube for older semesters)
2. Read the corresponding xv6 book chapter BEFORE the lab
3. Do EVERY lab — they are the entire point. Labs are 70% of the grade for a reason
4. Keep a "systems journal" — document every bug you hit and how you fixed it
5. Time budget: ~15-20 hours/week for 12 weeks

**Key Labs to Prioritize** (most relevant to sandboxing roles):
- **Lab: Page Tables** — This is the foundation of VM isolation. You'll implement virtual memory mappings in xv6. _"You thought you understood virtual memory from reading about it. The lab will prove otherwise."_
- **Lab: Traps** — How the kernel handles transitions between user/kernel mode. This IS the security boundary in sandboxing.
- **Lab: Locks** — Concurrency is the #1 source of bugs in production systems.

---

### Course 2: MIT 6.5840 — Distributed Systems

> **Real Estate Equivalent**: Multi-City Portfolio Management — Keeping properties in sync across SF, NYC, and Seattle when communication is unreliable

**Course URL**: https://pdos.csail.mit.edu/6.824/ | [Schedule (Spring 2024)](http://nil.csail.mit.edu/6.5840/2024/schedule.html)

**Instructors**: Prof. Robert Morris, Prof. Frans Kaashoek

**What You'll Learn** (mapped to JD skills):

| Lab / Topic | Real Estate Analogy | JD Skill It Builds |
|---|---|---|
| **Lab 1: MapReduce** | Delegating property inspections across 100 inspectors, then merging reports | Distributed data processing, worker coordination |
| **Lab 2: Raft (consensus)** | Getting 5 regional managers to agree on a new rent price even if 2 are unreachable | Consensus algorithms, leader election, log replication |
| **Lab 3: KV Store on Raft** | Building the property management database that survives office fires | Fault-tolerant storage, state machine replication |
| **Lab 4: Sharded KV Store** | Splitting the portfolio database by region for scalability — SF properties in one database, NYC in another | Data partitioning, shard migration, distributed transactions |
| **Lab 5: Final project** | Capstone — design your own distributed property management system | End-to-end distributed system design |
| **Lectures: GFS, Zookeeper, Spanner** | Case studies of how the biggest real estate empires manage their portfolios | Production distributed systems design patterns |
| **Lectures: Fault tolerance, linearizability** | What happens when the SF office burns down — does NYC still have all the records? | Consistency models, replication strategies |

**How to Study**:
1. Read the assigned paper BEFORE each lecture (the papers are the textbook)
2. Labs are in Go — learn Go basics first if needed (A Tour of Go is sufficient)
3. The Raft lab (Lab 2) is the hardest and most valuable. Budget extra time.
4. Run tests 100+ times — distributed systems bugs are non-deterministic
5. Time budget: ~20 hours/week for 14 weeks

**Key Papers to Deeply Understand**:
- **Raft** (Ongaro & Ousterhout) — The consensus algorithm. In real estate terms: how do 5 property managers stay in perfect agreement about every decision?
- **GFS** (Ghemawat et al.) — Google's distributed file system. The blueprint for storing petabytes across thousands of machines.
- **Zookeeper** — The "notary service" of distributed systems. Coordinates locks, configuration, and leader election.

---

### Course 3: MIT 6.172 — Performance Engineering of Software Systems

> **Real Estate Equivalent**: Structural Optimization — Making buildings stronger, lighter, and cheaper without sacrificing safety

**Course URL**: [MIT OCW (Fall 2018)](https://ocw.mit.edu/courses/6-172-performance-engineering-of-software-systems-fall-2018/)

**Instructors**: Prof. Charles Leiserson, Prof. Julian Shun

**Language**: C (this is intentional — you need to understand what the machine actually does)

**What You'll Learn** (mapped to JD skills):

| Topic | Real Estate Analogy | JD Skill It Builds |
|---|---|---|
| **Lecture 1: Matrix multiplication optimization** | Taking a building from 10 units to 100 units in the same footprint through clever floor plans | Algorithmic optimization, understanding performance gaps |
| **Cache optimization** | Putting frequently needed tools in the tool belt, not the truck | Cache hierarchies, spatial/temporal locality, cache-oblivious algorithms |
| **Instruction-level parallelism** | Having one worker do framing AND electrical simultaneously (pipelining) | CPU pipeline, branch prediction, SIMD |
| **Multithreading & parallelism** | Hiring 16 crews to work 16 units simultaneously | Pthreads, OpenCilk, work-stealing schedulers |
| **Memory allocation** | Efficient warehouse management — where to store materials for fastest access | Custom allocators, free lists, memory pools |
| **Synchronization** | Coordinating 16 crews so they don't run into each other in the hallway | Lock-free data structures, transactional memory |
| **Profiling & measurement** | Bringing in a building inspector with thermal cameras | perf, Valgrind, Cachegrind, accurate benchmarking |
| **Final project: Leiserchess** | Build the fastest, most efficient building you can, then compete against other architects | End-to-end performance optimization under constraints |

**How to Study**:
1. All lectures are on MIT OCW with video — watch them
2. Homework and projects available on OCW
3. Install `perf` on your Linux machine — you'll use it constantly
4. Time budget: ~18 hours/week for 14 weeks

**Why This Course Matters for Sandboxing**:
The JD says "optimize kernel params and VM configs to reduce inference latency." That's EXACTLY what this course teaches you to think about — where are the bottlenecks? Is it the algorithm, the cache, the memory allocator, the scheduler, or the hardware? You can't optimize what you can't measure.

---

## The Construction Plan: Projects Roadmap

Theory without practice is blueprints without buildings. Here are progressive projects that teach JD skills through hands-on construction.

### Phase 1 Projects: The Building Inspector Track

> Each project builds on the last. Don't skip ahead — you need the foundation.

#### Project 1.1: "The First Apartment" — Containerize & Deploy a Service

**Real Estate Analogy**: Build your first apartment unit and get it permitted

**What You'll Build**:
- A simple HTTP API (Python/FastAPI or Go) that executes user-submitted code snippets
- Dockerize it with a multi-stage build
- Deploy to a single machine with Docker Compose
- Add basic health checks and logging

**Skills Practiced**:
- Docker fundamentals (Dockerfile, images, layers, volumes)
- Container networking
- Basic observability (structured logging)
- Python or Go backend development

**Acceptance Criteria**:
- [ ] Service runs in a container, accepts code via POST, returns output
- [ ] Container has resource limits (CPU, memory) set in docker-compose
- [ ] Logs are structured JSON, collected to stdout
- [ ] Health check endpoint returns status

---

#### Project 1.2: "The Apartment Complex" — Kubernetes Orchestration

**Real Estate Analogy**: Scale from one apartment to an entire complex with a property management company

**What You'll Build**:
- Deploy Project 1.1 to a local Kubernetes cluster (kind or minikube)
- Implement Deployments, Services, ConfigMaps, and resource quotas
- Add horizontal pod autoscaling (HPA)
- Implement network policies for pod-to-pod isolation

**Skills Practiced**:
- Kubernetes core objects and lifecycle
- Resource management (requests, limits, quotas) — the HOA rules
- Network policies — property line enforcement
- kubectl debugging (logs, exec, describe, port-forward)

**Acceptance Criteria**:
- [ ] Service runs on K8s with 3 replicas
- [ ] HPA scales based on CPU utilization
- [ ] Network policies restrict ingress/egress
- [ ] Resource quotas prevent any pod from consuming more than its share
- [ ] Can perform a rolling update with zero downtime

---

#### Project 1.3: "The Security System" — Linux Isolation Primitives

**Real Estate Analogy**: Install the property lines, security fences, and HOA rules yourself — no property management company

**What You'll Build**:
- A sandbox launcher written in Go or Python that uses Linux primitives directly:
  - **Namespaces** (PID, NET, MNT, UTS, USER) — property lines
  - **cgroups v2** — resource limits (HOA rules)
  - **seccomp-bpf** — building code enforcement
- Execute untrusted code inside the sandbox
- Compare isolation quality against a plain Docker container

**Skills Practiced**:
- Linux namespaces (the actual property line system)
- cgroups v2 resource control (the actual HOA limit system)
- seccomp-bpf syscall filtering (the actual building code)
- Understanding what Docker actually does under the hood

**Key Learning**: Docker is just a nice UI on top of these primitives. When you build a sandbox from scratch, you understand exactly what "container isolation" means — and more importantly, where it's weak.

**Acceptance Criteria**:
- [ ] Sandbox creates isolated PID, NET, MNT namespaces
- [ ] cgroups limit CPU to 1 core, memory to 256MB
- [ ] seccomp blocks dangerous syscalls (mount, reboot, ptrace, etc.)
- [ ] Untrusted code cannot see host processes, files, or network
- [ ] Write a comparison doc: "What does Docker do vs. what I built?"

---

#### Project 1.4: "The Portfolio" — Distributed Sandbox Orchestrator

**Real Estate Analogy**: Manage sandboxes across multiple machines like a property portfolio across cities

**What You'll Build**:
- A distributed system that manages sandbox lifecycle across multiple nodes
- Central API server receives code execution requests
- Worker nodes (2-3) spin up sandboxes (from Project 1.3) to execute code
- Results streamed back via SSE or gRPC
- Basic observability: Prometheus metrics, Grafana dashboards

**Skills Practiced**:
- Distributed systems design (the portfolio management)
- gRPC or HTTP service mesh (the inter-office communication system)
- Prometheus + Grafana (the property inspection dashboard)
- Fault tolerance (what happens when a worker dies mid-execution?)
- Queue-based job distribution (the work order dispatch system)

**Acceptance Criteria**:
- [ ] API server distributes work across 2+ worker nodes
- [ ] Workers execute code in isolated sandboxes
- [ ] System handles worker failure gracefully (requeue the job)
- [ ] Prometheus metrics: sandbox creation rate, execution latency, error rate
- [ ] Grafana dashboard showing real-time system health

---

#### Project 1.5: "The Cloud Development" — GCP Deployment & IaC

**Real Estate Analogy**: Take your local property business national — move to the big leagues with cloud infrastructure

**What You'll Build**:
- Deploy Project 1.4 to GCP using Terraform
- Use GKE (Google Kubernetes Engine) for orchestration
- Cloud Run or Cloud Functions for serverless sandbox execution (alternative path)
- Cloud Monitoring + Cloud Logging for observability
- IAM policies for least-privilege access

**Skills Practiced**:
- Terraform (architectural blueprints for cloud)
- GCP services (GKE, Cloud Run, Cloud Monitoring, IAM)
- Production deployment patterns
- Cost optimization (right-sizing, preemptible instances)

**Acceptance Criteria**:
- [ ] Entire stack deployed via `terraform apply`
- [ ] GKE cluster running sandbox workers
- [ ] Cloud Monitoring dashboards and alerts configured
- [ ] IAM follows least-privilege principle
- [ ] Documented cost estimate and optimization strategies

---

### Phase 2 Projects: The Licensed Architect Track

> You've managed buildings. Now you're going to design the structural systems themselves. These projects directly mirror the representative projects listed in Anthropic's Software Engineer, Sandboxing (Systems) JD. Each one involves real ML workloads, measurable performance improvements, and production-grade engineering.

#### Prerequisite: "Soil Science" — xv6 Operating System Labs

> **This is coursework, not a portfolio project.** Think of it as studying for your architect's license exam — mandatory, but you don't show it to clients.

Complete MIT 6.1810 labs (page tables, traps, system calls, scheduling, file system). This gives you the kernel literacy required for everything below. Do this concurrently with Phase 1 projects, not sequentially after them.

**Acceptance Criteria**:
- [ ] All 6.1810 labs passing
- [ ] Can explain from memory: page table walks, trap frames, context switch mechanics
- [ ] Written reflection mapping xv6 concepts to real sandboxing primitives

---

#### Project 2.1: "The Custom Foundation" — LLM Inference-Optimized microVM

> **JD Match**: *"Creating lightweight virtualization solutions tailored for AI inference"*
>
> **Real Estate Analogy**: Design a prefab home factory specifically engineered for data center tenants — every square inch optimized for compute density. Standard prefabs (generic Firecracker) waste space with features your tenants don't need. You're building custom units where the plumbing (I/O), electrical (CPU pinning), and HVAC (memory) are purpose-built for one type of occupant: LLM inference workloads.

**What You'll Build**:
- Fork or extend **Firecracker** (or Cloud Hypervisor) to create an inference-specialized microVM:
  - **Custom guest kernel config**: Strip ~80% of unnecessary modules (no USB, no sound, no legacy drivers). Enable huge pages, KSM (Kernel Same-page Merging), and transparent huge pages for model weight regions
  - **vCPU pinning**: Pin guest vCPUs to specific host cores, avoiding cross-NUMA scheduling. Configure `isolcpus` on the host to dedicate cores exclusively to microVM workloads
  - **Balloon driver**: Implement dynamic memory adjustment between host and guest — reclaim unused guest memory during low-load periods, expand during batch inference
  - **GPU passthrough**: Configure VFIO-based GPU passthrough (or virtio-gpu for shared GPU) so the microVM can run CUDA workloads directly
  - **Snapshot/restore optimization**: Create VM snapshots with model weights already loaded in memory — "warm starts" that skip model loading entirely
- Run actual LLM inference inside the microVM: **vLLM serving Llama 3 8B** (or llama.cpp with a quantized 70B)
- Benchmark against three baselines: bare metal, Docker container, and stock Firecracker

**Tech Stack**: Rust, KVM API (`/dev/kvm` ioctls), virtio device models, VFIO, Linux kernel config (`make menuconfig`), Firecracker/Cloud Hypervisor source code

**Key Metrics to Measure**:
- Cold start latency (target: <150ms to first inference)
- Warm start latency via snapshot/restore (target: <30ms)
- Inference throughput: tokens/sec at batch size 1, 8, 32
- Memory overhead per microVM (target: <5MB VMM overhead)
- p99 latency comparison: microVM vs. bare metal (target: <5% overhead)

**Acceptance Criteria**:
- [ ] Custom guest kernel boots in microVM with only ML-relevant modules
- [ ] vLLM or llama.cpp runs inference end-to-end inside the microVM
- [ ] GPU passthrough or virtio-gpu functional for CUDA workloads
- [ ] Snapshot/restore with pre-loaded model weights operational
- [ ] Benchmark report: "LLM Inference in Optimized microVMs — Performance Analysis" with flame graphs, latency distributions, and throughput curves
- [ ] Architecture doc explaining every optimization decision and its measured impact

---

#### Project 2.2: "The Smart Elevator" — BPF-Based ML Workload Scheduler

> **JD Match**: *"Developing specialized I/O schedulers to prioritize ML workloads"*
>
> **Real Estate Analogy**: Your high-rise has one elevator system, but 80% of the traffic is freight (GPU data transfers). The default elevator (CFS/EEVDF scheduler) treats a delivery truck the same as a resident going to the lobby. You're building a custom elevator controller that recognizes freight, gives it express lanes, and coordinates all delivery trucks to arrive at the loading dock simultaneously (gang scheduling) — because if one truck is late, the entire shipment is delayed.

**What You'll Build**:

**Part A: Custom CPU Scheduler via sched_ext**
- Write a **sched_ext** scheduler following the `scx_rustland` architecture:
  - **Rust user-space component**: Complex scheduling logic — task classification, priority assignment, NUMA-aware CPU selection, and historical latency tracking
  - **BPF kernel component**: Minimal fast-path — task enqueue/dequeue, dispatch queue management, safety watchdog
  - Communication between user-space and kernel via **ring buffers**
- Scheduler policies:
  - **ML task detection**: Identify inference/training processes by cgroup label (e.g., `/ml-inference/*`), process name patterns, or `sched_setattr` hints
  - **GPU jitter reduction**: When an ML task is about to launch a GPU kernel (detected via tracepoint on `ioctl` to `/dev/nvidia*`), pin it to a dedicated core and boost its priority to minimize CPU scheduling delay before GPU dispatch
  - **NUMA affinity**: Automatically schedule ML tasks on the NUMA node closest to their allocated GPU (query topology from `/sys/devices/system/node/`)
  - **Gang scheduling**: For distributed training, ensure all ranks (processes across VMs) are co-scheduled simultaneously — if rank 2 of 4 is descheduled, the all-reduce stalls ALL ranks
- Safety: If your scheduler fails to schedule a task within 30s, sched_ext automatically falls back to default CFS

**Part B: I/O Prioritization via BPF**
- Attach BPF programs to the Linux block layer (`blk-mq` tracepoints):
  - **Priority queue**: Model weight reads and KV cache page-ins get highest I/O priority
  - **Checkpoint deadline**: Training checkpoint writes get deadline-based scheduling (must complete within N seconds or alert)
  - **Background demotion**: System logs, metrics collection, and non-ML I/O get demoted to best-effort
- Integrate with `io_uring` for async I/O submission from the ML workload side

**Benchmarks** (run on real workloads):
- PyTorch DDP ResNet-50 training: measure iteration time variance (jitter) with custom scheduler vs. CFS
- vLLM Llama 3 8B serving: measure p50/p99/p999 token latency under concurrent load
- Training checkpoint write latency with I/O prioritization vs. default

**Tech Stack**: sched_ext framework, BPF/eBPF (libbpf), Rust (user-space scheduler), C (BPF programs), `io_uring`, Linux block layer, `perf sched` for analysis

**Reference Material**:
- [sched_ext: BPF-Powered CPU Schedulers in the Linux Kernel](https://free5gc.org/blog/20250305/20250305/)
- [gpu_ext: Extensible OS Policies for GPUs via eBPF](https://arxiv.org/html/2512.12615) (Dec 2025) — 2x throughput with BPF GPU policies
- [Linux Plumbers 2025: sched_ext GPU awareness talks](https://lpc.events/event/19/sessions/229/)
- `scx_rustland` source code in the sched_ext repo

**Acceptance Criteria**:
- [ ] sched_ext scheduler loads dynamically, falls back safely on failure
- [ ] ML tasks are correctly classified and prioritized (verified via `/proc/sched_debug`)
- [ ] Gang scheduling demonstrated: 4 PyTorch DDP ranks co-scheduled with <1ms skew
- [ ] I/O prioritization measurably reduces model load time and checkpoint write latency
- [ ] Benchmark report: "ML-Aware CPU and I/O Scheduling — Performance Impact on LLM Inference and Distributed Training"
- [ ] Comparison table: Custom scheduler vs. CFS vs. EEVDF across all workloads

---

#### Project 2.3: "The Water System" — NUMA-Aware Memory Allocator for LLM Serving

> **JD Match**: *"Implementing custom memory management schemes for large-scale distributed training"*
>
> **Real Estate Analogy**: You're designing the water distribution system for a 50-story mixed-use building where every floor has radically different plumbing needs. The penthouse restaurant (GPU attention layers) needs direct, high-pressure water lines with zero lag. The office floors (CPU embedding layers) can share mains. The basement storage (cold KV cache) uses a cistern that fills overnight. A standard uniform plumbing system wastes pressure on floors that don't need it and starves floors that do. You're building **zone-based water management** — each zone gets exactly the pressure and volume it needs.

**What You'll Build**:

**Part A: NUMA-Aware Model Weight Allocator**
- Implement a custom memory allocator (C library with Python bindings, or Rust with FFI) that:
  - **Queries NUMA topology** at startup: which CPU sockets, which memory nodes, which GPUs are on which NUMA node (`libnuma`, `/sys/devices/system/node/`)
  - **Places model weight tensors** on the NUMA node local to the GPU that will consume them — attention head weights go on GPU-local DRAM, not remote DRAM
  - **Uses huge pages** (2MB via `madvise(MADV_HUGEPAGE)` or 1GB via `hugetlbfs`) for model weight regions to reduce TLB misses. A 70B model in FP16 = ~140GB = ~70 million 4KB pages = massive TLB pressure. With 2MB huge pages, that's ~70K entries. With 1GB pages, ~140.
  - **Memory binding**: Use `mbind()` / `set_mempolicy()` to enforce NUMA placement, preventing the kernel from migrating pages to remote nodes

**Part B: PagedAttention-Inspired KV Cache Manager**
- Implement a virtual memory-style KV cache manager (inspired by vLLM's PagedAttention):
  - **Block-based allocation**: Divide KV cache memory into fixed-size blocks (like OS pages). Allocate blocks on demand per sequence, not pre-allocated per max sequence length
  - **Block table**: Maintain a mapping table (like a page table) from logical KV positions to physical memory blocks
  - **Copy-on-write**: For beam search or parallel sampling, share KV blocks between sequences and only copy when one sequence diverges
  - **Memory defragmentation**: Periodically compact KV blocks to reduce fragmentation (like OS memory compaction)
  - **Tiered storage**: Hot blocks (recent tokens) in GPU HBM → warm blocks in CPU DRAM → cold blocks on NVMe SSD, with transparent migration

**Part C: Integration & Benchmarking**
- Integrate as a custom allocator backend for **vLLM** or **llama.cpp**
- Measure:
  - **TLB miss reduction**: Before/after huge pages (using `perf stat -e dTLB-load-misses`)
  - **NUMA remote access reduction**: Before/after NUMA-aware placement (using `perf stat -e node-load-misses`)
  - **KV cache utilization**: What % of allocated memory contains actual token state? (baseline: 20-38% in naive systems per vLLM paper)
  - **End-to-end inference latency**: p50/p99 token generation time with your allocator vs. default `malloc`

**Tech Stack**: C or Rust, `mmap`, `mbind`/`set_mempolicy`, `madvise`, `hugetlbfs`, `libnuma`/`numactl`, `perf`/`cachegrind`/`numastat`, Python ctypes/cffi for integration

**Reference Material**:
- [vLLM PagedAttention Paper](https://arxiv.org/pdf/2309.06180) — "Efficient Memory Management for LLM Serving"
- [KTransformers (SOSP '25)](https://madsys.cs.tsinghua.edu.cn/publication/ktransformers-unleashing-the-full-potential-of-cpu/gpu-hybrid-inference-for-moe-models/SOSP25-chen.pdf) — NUMA-aware tensor parallelism, 1.63x throughput
- [CXL-Aware Memory Allocator](https://arxiv.org/html/2507.03305v2) — per-tensor NUMA-aware allocation, 21% improvement
- [NVIDIA: CPU-GPU Memory Sharing for LLM Inference](https://developer.nvidia.com/blog/accelerate-large-scale-llm-inference-and-kv-cache-offload-with-cpu-gpu-memory-sharing/)

**Acceptance Criteria**:
- [ ] Allocator correctly queries NUMA topology and places tensors on GPU-local nodes
- [ ] Huge page allocation verified (`/proc/meminfo` HugePages_Total)
- [ ] PagedAttention-style KV cache with block table, CoW, and defragmentation working
- [ ] TLB miss reduction ≥50% measured with `perf`
- [ ] NUMA remote access reduction ≥60% measured with `numastat`
- [ ] KV cache utilization ≥85% (up from ~30% baseline)
- [ ] Benchmark report: "NUMA-Aware Memory Management for LLM Inference — From 30% to 85% KV Cache Utilization"

---

#### Project 2.4: "The Skywalks" — Inter-VM Communication for Distributed Training

> **JD Match**: *"Enhancing communication between VMs for distributed training workloads"*
>
> **Real Estate Analogy**: You have 4 adjacent buildings (microVMs) that need to move massive freight (gradient tensors) between them every 200ms. The current method: load freight onto a truck (TCP), drive it out one building's garage, across the street, and into the next building's garage. That's a 3-mile round trip for buildings that share a wall. You're building **skywalks** — enclosed elevated walkways with conveyor belts that move freight directly between buildings through shared walls (shared memory), bypassing the street (network stack) entirely.

**What You'll Build**:

**Part A: Shared Memory Transport**
- Implement a **shared memory ring buffer** between Firecracker microVMs:
  - Host allocates a hugepage-backed shared memory region
  - Each microVM maps the region via **ivshmem** (inter-VM shared memory) virtual PCI device
  - Ring buffer protocol: lock-free SPSC (single-producer single-consumer) or MPMC ring with cache-line-aligned slots to avoid false sharing
  - Zero-copy: producer writes gradient tensor directly into shared buffer, consumer reads in-place — no `memcpy`, no serialization
- Control plane: **virtio-vsock** for metadata exchange (tensor shapes, synchronization signals)
- Data plane: shared memory for bulk gradient transfer

**Part B: Custom PyTorch DDP Communication Backend**
- Implement a PyTorch `ProcessGroupBackend` plugin that:
  - Replaces TCP/NCCL with your shared-memory transport for inter-VM all-reduce
  - **All-reduce implementation**: Ring all-reduce over shared memory — each VM reads from left neighbor's buffer, reduces with local gradients, writes to right neighbor's buffer
  - Supports common collective operations: `all_reduce`, `broadcast`, `all_gather`
  - Handles gradient quantization (FP32 → FP16 → INT8) in the communication layer to reduce bandwidth
- Run **PyTorch DDP training** across 2-4 Firecracker microVMs, each VM acting as one training rank

**Part C: Performance Analysis**
- **eBPF monitoring**: Attach probes to measure:
  - Communication latency per all-reduce call (microseconds)
  - Bandwidth utilization of shared memory channel
  - CPU overhead of the communication backend
  - Time spent in synchronization barriers vs. actual data transfer
- Benchmark against:
  - **TCP-based NCCL**: Standard inter-VM communication over virtual network
  - **Bare-metal NCCL**: No VM overhead, direct hardware access (the ceiling)
  - **Your shared-memory backend**: The goal is to approach bare-metal performance

**Tech Stack**: C/Rust (shared memory transport), Python (PyTorch backend plugin), virtio-vsock, ivshmem, DPDK virtio-user (optional for network-path comparison), eBPF, PyTorch DDP

**Reference Material**:
- [ACRN Inter-VM Shared Memory Communication](https://projectacrn.github.io/latest/tutorials/enable_ivshmem.html)
- [DPDK Virtio-User for Container Networking](http://doc.dpdk.org/guides-25.11/howto/virtio_user_for_container_networking.html)
- [Shared-Memory Optimizations for Inter-VM Communication (ACM Survey)](https://dl.acm.org/doi/abs/10.1145/2847562)
- [NCCL: Optimized Primitives for Inter-GPU Communication](https://developer.nvidia.com/nccl)

**Acceptance Criteria**:
- [ ] Shared memory ring buffer functional between 2+ Firecracker microVMs
- [ ] PyTorch DDP training completes successfully across microVMs using custom backend
- [ ] All-reduce latency within 2x of bare-metal NCCL (measured via eBPF)
- [ ] Zero-copy verified: no intermediate buffers in data path
- [ ] Training convergence matches baseline (same loss curve as TCP/NCCL)
- [ ] Benchmark report: "Inter-VM Communication for Distributed Training — Shared Memory vs. TCP vs. Bare Metal"

---

#### Project 2.5: "The Building Inspector's Dashboard" — eBPF Observability for Sandboxed ML Workloads

> **JD Match**: *"Building monitoring and instrumentation tools to identify system-level bottlenecks"*
>
> **Real Estate Analogy**: You're installing a smart building management system with sensors embedded in every wall, pipe, wire, and elevator shaft. Not just smoke detectors (crash alerts) — **thermal cameras** that see heat patterns through walls (flame graphs), **flow meters** on every pipe junction (memory bandwidth), **vibration sensors** on every motor (scheduler latency), and a **central command center** (Grafana) that correlates all signals to predict failures before they happen. When a tenant calls to say "my apartment is cold," you already know it's because Pump 3B on Floor 7 is running at 40% capacity due to a clogged filter installed 3 weeks ago.

**What You'll Build**:

**Part A: eBPF Instrumentation Suite**
A collection of purpose-built eBPF programs, each targeting a specific bottleneck class:

| Program | What It Measures | Attachment Point | Real Estate Analogy |
|---|---|---|---|
| `sandbox-syscall-profiler` | Per-sandbox syscall latency histograms | `tracepoint/raw_syscalls/sys_enter` + `sys_exit` | Maintenance request response times per unit |
| `page-fault-tracker` | Major/minor page fault rates, NUMA migration events | `tracepoint/exceptions/page_fault_user` | Plumbing leak detection per floor |
| `sched-latency-monitor` | CPU runqueue wait time for ML tasks after GPU completion | `tracepoint/sched/sched_wakeup` + `sched_switch` | Elevator wait times per floor |
| `vm-network-analyzer` | Inter-VM bandwidth, latency, packet drops | `tracepoint/net/net_dev_xmit` + `kprobe/tcp_sendmsg` | Skywalk traffic flow and congestion |
| `memory-bandwidth-meter` | Per-NUMA-node memory bandwidth and remote access rates | `perf_event` hardware counters | Water pressure per zone |
| `gpu-cpu-correlator` | Time between GPU kernel completion and next CPU-side dispatch | `kprobe` on NVIDIA `ioctl` + `sched_switch` | Freight elevator turnaround time |

**Part B: Export & Visualization**
- Export all metrics to **Prometheus** via BPF map → user-space exporter → Prometheus scrape
- Pre-built **Grafana dashboards**:
  - **Sandbox Overview**: Per-sandbox health score, resource utilization, anomaly flags
  - **Scheduler Analysis**: Runqueue depth over time, ML task wait latency distribution, gang scheduling skew
  - **Memory Heatmap**: NUMA node utilization, page fault rates, huge page coverage
  - **Communication Monitor**: Inter-VM latency matrix, bandwidth utilization, dropped packets
- **Automated flame graph generation**: On-demand `perf record` → flame graph SVG via `inferno` or Brendan Gregg's FlameGraph tools

**Part C: Anomaly Detection**
- Establish **baseline syscall profiles** for healthy sandboxes (e.g., "a healthy vLLM sandbox makes ~X syscalls/sec with this distribution")
- Flag deviations: "Sandbox 47 has 10x more `futex` calls than baseline — likely lock contention"
- Implement alerting rules in Prometheus: page fault rate spike → NUMA migration storm → investigate placement

**Tech Stack**: eBPF (libbpf for production, bpftrace for prototyping), BCC, `perf_event` interface, Prometheus client library, Grafana, `inferno` (Rust flame graph generator), Python (exporter daemon)

**Reference Material**:
- *BPF Performance Tools* by Brendan Gregg (the bible)
- [gpu_ext observability tools](https://arxiv.org/html/2512.12615) — eBPF on GPU devices
- [bpftrace reference guide](https://github.com/iovisor/bpftrace/blob/master/docs/reference_guide.md)

**Acceptance Criteria**:
- [ ] All 6 eBPF programs functional and producing correct metrics
- [ ] Prometheus scraping all metrics with <1s latency
- [ ] Grafana dashboards showing real-time sandbox health across all dimensions
- [ ] Anomaly detection correctly identifies at least 3 injected failure modes (lock contention, NUMA thrashing, I/O starvation)
- [ ] Flame graph generation works on-demand for any running sandbox
- [ ] Documentation: "eBPF Observability for Sandboxed ML Workloads — Operator's Guide"

---

#### Project 2.6: "The Development" — Production LLM Inference Sandbox Platform (Capstone)

> **JD Match**: ALL six representative projects integrated into one system
>
> **Real Estate Analogy**: The entire mixed-use development — but not a cookie-cutter suburban subdivision. This is a purpose-built, smart, energy-efficient, high-density data center campus where every system (foundation, plumbing, electrical, elevator, security, building management) is custom-designed and integrated. The penthouse units (GPU nodes) have direct water lines (NUMA-aware memory). The skywalks (shared memory) move freight between buildings at conveyor-belt speed. The elevator system (BPF scheduler) knows which freight is time-sensitive. The building inspector (eBPF observability) has sensors in every wall. And the whole thing was built from prefab modules (optimized microVMs) that snap together in under 150ms.

**What You'll Build**:
- A production-grade LLM inference sandbox platform that integrates ALL prior Phase 2 work:
  - **Execution substrate**: Inference-optimized microVMs from Project 2.1 (custom kernel, huge pages, GPU passthrough, snapshot/restore)
  - **CPU/IO scheduling**: BPF-based ML scheduler from Project 2.2 (sched_ext for CPU, BPF for I/O priority)
  - **Memory management**: NUMA-aware allocator from Project 2.3 (tensor placement, KV cache paging, huge pages)
  - **Inter-VM communication**: Shared memory transport from Project 2.4 (for multi-VM tensor-parallel inference)
  - **Observability**: eBPF monitoring suite from Project 2.5 (syscall profiling, scheduler analysis, memory heatmaps)

**System Architecture**:
```
                                    ┌─────────────────────────┐
                                    │    API Gateway (gRPC)    │
                                    │  Accept inference reqs   │
                                    └────────────┬────────────┘
                                                 │
                                    ┌────────────▼────────────┐
                                    │     Orchestrator        │
                                    │  - VM pool management   │
                                    │  - Request routing      │
                                    │  - Auto-scaling         │
                                    └────────────┬────────────┘
                                                 │
                        ┌────────────────────────┼────────────────────────┐
                        │                        │                        │
               ┌────────▼────────┐      ┌────────▼────────┐     ┌────────▼────────┐
               │  microVM Pool   │      │  microVM Pool   │     │  microVM Pool   │
               │  (GPU Node 0)   │◄────►│  (GPU Node 1)   │◄───►│  (GPU Node 2)   │
               │                 │ shared│                 │shared│                 │
               │  ┌───────────┐  │memory │  ┌───────────┐  │mem  │  ┌───────────┐  │
               │  │ vLLM +    │  │  ◄──► │  │ vLLM +    │  │◄──► │  │ vLLM +    │  │
               │  │ Custom    │  │       │  │ Custom    │  │     │  │ Custom    │  │
               │  │ Allocator │  │       │  │ Allocator │  │     │  │ Allocator │  │
               │  └───────────┘  │       │  └───────────┘  │     │  └───────────┘  │
               └────────┬────────┘       └────────┬────────┘     └────────┬────────┘
                        │                         │                       │
               ┌────────▼─────────────────────────▼───────────────────────▼────────┐
               │                    Host Kernel Layer                               │
               │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
               │  │ sched_ext    │  │ BPF I/O      │  │ eBPF Observability Suite │ │
               │  │ ML Scheduler │  │ Prioritizer  │  │ (Prometheus + Grafana)   │ │
               │  └──────────────┘  └──────────────┘  └──────────────────────────┘ │
               └───────────────────────────────────────────────────────────────────┘
```

**End-to-End Flow**:
1. Client sends inference request via gRPC
2. Orchestrator selects a microVM from the warm pool (snapshot/restore, <30ms)
3. Request routed to microVM running vLLM with NUMA-aware allocator
4. For tensor-parallel inference: shared memory all-reduce across microVMs on same host
5. BPF scheduler ensures ML tasks get priority CPU time, I/O prioritizer fast-tracks model weight loads
6. eBPF suite monitors every layer, exports to Prometheus/Grafana
7. Tokens streamed back to client via SSE

**Key Demonstration**:
- Run vLLM serving Llama 3 8B (or 70B with tensor parallelism across VMs)
- Compare against **naive baseline**: stock Docker container, default kernel, TCP networking, no observability
- Show measurable improvements across every dimension:

| Metric | Naive Baseline | Your Platform | Improvement |
|---|---|---|---|
| Cold start latency | ~2-5s (Docker pull + model load) | <150ms (snapshot/restore) | 10-30x |
| p99 token latency | Baseline measurement | Lower via scheduler + memory opts | Measurable |
| KV cache utilization | ~30% (vLLM default) | ~85%+ (your paged allocator) | ~3x |
| NUMA remote accesses | High (random placement) | Minimal (NUMA-aware) | ≥60% reduction |
| Inter-VM all-reduce | TCP latency | Shared memory latency | Target 2-5x |
| Observability | None / basic metrics | Full eBPF stack | Qualitative |

**Security Stack** (non-negotiable — this is sandboxing):
- KVM hardware virtualization (strongest isolation boundary)
- seccomp-bpf syscall filtering on VMM process
- Namespace isolation (PID, NET, MNT, USER)
- Firecracker jailer (chroot + cgroup + seccomp)
- No shared kernel between host and guest

**Acceptance Criteria**:
- [ ] End-to-end: submit prompt via API → spin up optimized microVM → run inference → stream tokens back
- [ ] Handles 50+ concurrent inference requests with graceful queuing
- [ ] All 5 subsystems integrated and working together (microVM + scheduler + memory + comms + observability)
- [ ] Benchmark report with comparison table showing improvement across every metric
- [ ] Security audit document: threat model, isolation boundaries, escape vector analysis
- [ ] Full Grafana dashboard showing real-time platform health
- [ ] Architecture document written as a **system design interview presentation** — diagrams, trade-offs, alternatives considered, why you chose what you chose
- [ ] Public GitHub repo with clean README, architecture diagram, and benchmark results
- [ ] **This is what you present at the Anthropic interview.**

---

## The Inspection Checklist: Milestones & Verification

### Phase 1 Milestones (Months 1-6): Building Inspector Certification

```
Month 1-2: Foundation Laying
├── [ ] Complete "A Tour of Go" or solidify Python backend skills
├── [ ] Project 1.1 complete (containerized code executor)
├── [ ] Start MIT 6.1810 (OS Engineering) — Labs 1-3
└── [ ] Read: "The Linux Programming Interface" Ch. 1-10

Month 3-4: Framing & Plumbing
├── [ ] Project 1.2 complete (Kubernetes orchestration)
├── [ ] Project 1.3 complete (Linux isolation primitives from scratch)
├── [ ] MIT 6.1810 — Labs 4-6 (page tables, traps)
├── [ ] Start MIT 6.5840 (Distributed Systems) — Labs 1-2
└── [ ] Read: Container Security by Liz Rice (the definitive container security book)

Month 5-6: Inspection & Certification
├── [ ] Project 1.4 complete (distributed sandbox orchestrator)
├── [ ] Project 1.5 complete (GCP deployment with Terraform)
├── [ ] MIT 6.5840 — Labs 3-4 (Raft, sharded KV store)
├── [ ] Can whiteboard: "Design a multi-tenant code execution platform"
└── [ ] CHECKPOINT: Could you pass an Infrastructure Engineer interview? Practice.
```

### Phase 2 Milestones (Months 7-18): Architect's License

> Phase 2 is longer because the projects are production-grade. This isn't tutorial work — you're building systems that produce measurable performance improvements on real ML workloads.

```
Month 7-8: Soil Science & Foundation Pouring
├── [ ] xv6 prerequisite labs complete (should have started in Phase 1)
├── [ ] Project 2.1 started (inference-optimized microVM)
│       └── Custom guest kernel config, vCPU pinning, Firecracker fork
├── [ ] Start MIT 6.172 (Performance Engineering) — first 6 lectures
├── [ ] Read: "Linux Kernel Development" by Robert Love (3rd Edition)
├── [ ] Read: Firecracker paper (NSDI '20) + Firecracker source walkthrough
└── [ ] Can explain: "How does KVM create a VM? What does Firecracker do differently than QEMU?"

Month 9-10: Core Systems — Virtualization & Scheduling
├── [ ] Project 2.1 complete (microVM boots, vLLM runs inference, benchmarks done)
├── [ ] Project 2.2 started (BPF-based ML scheduler)
│       └── sched_ext hello-world → ML task detection → NUMA-aware pinning
├── [ ] MIT 6.172 — lectures 7-14 (cache optimization, parallelism, profiling)
├── [ ] Read: "BPF Performance Tools" by Brendan Gregg, Chapters 1-8
├── [ ] Study sched_ext source code (scx_rustland, scx_layered)
└── [ ] Can explain: "How does sched_ext work? What are the safety guarantees?"

Month 11-12: Memory & Communication
├── [ ] Project 2.2 complete (scheduler benchmarked against CFS on ML workloads)
├── [ ] Project 2.3 started (NUMA-aware memory allocator)
│       └── NUMA topology query → huge page allocation → KV cache paging
├── [ ] Project 2.4 started (inter-VM shared memory communication)
│       └── ivshmem ring buffer → PyTorch DDP backend
├── [ ] Read: vLLM PagedAttention paper + KTransformers SOSP '25
├── [ ] Read: ACRN ivshmem docs + DPDK virtio-user guide
└── [ ] Can explain: "How does PagedAttention manage GPU memory like an OS manages RAM?"

Month 13-14: Observability & Integration
├── [ ] Project 2.3 complete (allocator integrated with vLLM, TLB miss reduction measured)
├── [ ] Project 2.4 complete (shared-memory all-reduce benchmarked vs NCCL)
├── [ ] Project 2.5 started (eBPF observability suite)
│       └── 6 eBPF programs → Prometheus export → Grafana dashboards
├── [ ] MIT 6.172 — complete remaining lectures + Leiserchess project
└── [ ] Can explain: "Walk me through how you'd debug a latency spike in sandboxed LLM inference"

Month 15-16: Capstone Construction
├── [ ] Project 2.5 complete (observability suite with anomaly detection)
├── [ ] Project 2.6 started (capstone: production LLM inference sandbox platform)
│       └── Integrate all 5 subsystems, build orchestrator, wire gRPC API
├── [ ] Benchmark: measure every metric in the comparison table
├── [ ] Security audit: document threat model and isolation boundaries
└── [ ] Architecture document first draft

Month 17-18: Polish & Launch
├── [ ] Project 2.6 complete (full platform operational)
├── [ ] Benchmark report finalized with flame graphs, latency distributions, throughput curves
├── [ ] Architecture document polished for system design interviews
├── [ ] Public GitHub repo live with clean README, diagrams, and results
├── [ ] CHECKPOINT: Could you pass a Systems Software Engineer interview? Mock interview.
└── [ ] Apply to Anthropic.
```

---

### Reading List: The Developer's Library

#### Phase 1 (Building Inspector)
| Book | Real Estate Equivalent | Priority |
|---|---|---|
| *The Linux Programming Interface* — Michael Kerrisk | The building code handbook | Must-read, Chapters 1-10, 22-29, 44 |
| *Container Security* — Liz Rice | The fire safety inspection manual | Must-read |
| *Designing Data-Intensive Applications* — Martin Kleppmann | The property portfolio management bible | Must-read |
| *Site Reliability Engineering* — Google | How Google manages 100,000 buildings | Recommended |
| *Kubernetes in Action* — Marko Luksa | The property management company operations manual | Reference |

#### Phase 2 (Architect)
| Book | Real Estate Equivalent | Priority |
|---|---|---|
| *Linux Kernel Development* — Robert Love | The structural engineering textbook | Must-read |
| *BPF Performance Tools* — Brendan Gregg | The smart building sensor installation manual | Must-read (Projects 2.2, 2.5) |
| *Computer Systems: A Programmer's Perspective* (CS:APP) — Bryant & O'Hallaron | The materials science textbook | Must-read for perf |
| *Understanding the Linux Kernel* — Bovet & Cesati | The deep geology survey | Deep reference |
| *Operating Systems: Three Easy Pieces* (OSTEP) — Arpaci-Dusseau | The accessible intro to soil science | Great companion to 6.1810 |
| *Programming Rust* — Blandy, Orendorff, Tindall | Modern engineered materials handbook | Must-read for Firecracker/sched_ext work |

#### Key Papers (Ordered by Project Relevance)
| Paper | Project | Why It Matters |
|---|---|---|
| *Firecracker: Lightweight Virtualization for Serverless Applications* (NSDI '20) | 2.1 | This IS the technology Anthropic builds on. Read the source code too. |
| *Efficient Memory Management for LLM Serving with PagedAttention* (SOSP '23) | 2.3 | OS-style virtual memory for KV cache. Your allocator project is inspired by this. |
| *KTransformers: CPU/GPU Hybrid Inference for MoE Models* (SOSP '25) | 2.3 | NUMA-aware tensor parallelism — 1.63x throughput. Direct template for your allocator. |
| *gpu_ext: Extensible OS Policies for GPUs via eBPF* (Dec 2025) | 2.2, 2.5 | eBPF on GPU devices — 2x throughput. The frontier of BPF-based ML scheduling. |
| *sched_ext: A BPF-Extensible Scheduler Class* (LWN) | 2.2 | The framework you'll build your ML scheduler on. Read this before touching code. |
| *Shared-Memory Optimizations for Inter-VM Communication* (ACM Survey) | 2.4 | Comprehensive survey of everything you'll implement in Project 2.4. |
| *Raft: In Search of an Understandable Consensus Protocol* | Phase 1 | Core distributed systems — you'll implement this in 6.5840 |
| *gVisor: Container Security Through Kernel Reimplementation* | General | Google's approach to sandboxing — alternative to Firecracker |
| *The Google File System* | Phase 1 | Foundational distributed storage paper |
| *Bubblewrap: Unprivileged Sandboxing Tool* | General | Used by Anthropic's sandbox-runtime on Linux |

---

## Resources & References

### Job Descriptions (Source Material)
- [Infrastructure Engineer, Sandboxing — Anthropic](https://job-boards.greenhouse.io/anthropic/jobs/5030680008)
- [Software Engineer, Sandboxing (Systems) — Anthropic](https://job-boards.greenhouse.io/anthropic/jobs/5025591008)
- [Software Engineer, Sandboxing — Anthropic](https://job-boards.greenhouse.io/anthropic/jobs/5083039008) (bonus: 3rd related role discovered)

### MIT Courses
- [MIT 6.1810 — Operating System Engineering (Fall 2023)](https://ocw.mit.edu/courses/6-1810-operating-system-engineering-fall-2023/)
- [MIT 6.5840 — Distributed Systems (Spring 2024)](http://nil.csail.mit.edu/6.5840/2024/schedule.html)
- [MIT 6.172 — Performance Engineering (Fall 2018)](https://ocw.mit.edu/courses/6-172-performance-engineering-of-software-systems-fall-2018/)

### Anthropic Open Source
- [anthropic-experimental/sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) — Anthropic's open-source sandboxing tool using bubblewrap (Linux) and Seatbelt (macOS)
- [Anthropic Engineering Blog: Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)

### Firecracker & microVMs
- [Firecracker GitHub](https://github.com/firecracker-microvm/firecracker)
- [How AWS's Firecracker Virtual Machines Work — Amazon Science](https://www.amazon.science/blog/how-awss-firecracker-virtual-machines-work)
- [How to sandbox AI agents in 2026: MicroVMs, gVisor & isolation strategies](https://northflank.com/blog/how-to-sandbox-ai-agents)

### BPF & Scheduling
- [sched_ext: BPF-Powered CPU Schedulers](https://free5gc.org/blog/20250305/20250305/) — Comprehensive sched_ext overview
- [gpu_ext: eBPF Policies for GPUs](https://arxiv.org/html/2512.12615) — eBPF directly on NVIDIA GPUs (Dec 2025)
- [Linux Plumbers 2025: sched_ext GPU Awareness](https://lpc.events/event/19/sessions/229/) — Future plans for ML-aware scheduling
- [sched_ext Igalia Blog Series](https://blogs.igalia.com/changwoo/sched-ext-a-bpf-extensible-scheduler-class-part-1/) — Deep technical walkthrough

### Memory Management for LLM
- [vLLM PagedAttention Paper](https://arxiv.org/pdf/2309.06180) — OS-style virtual memory for KV cache
- [KTransformers: NUMA-Aware MoE Inference (SOSP '25)](https://madsys.cs.tsinghua.edu.cn/publication/ktransformers-unleashing-the-full-potential-of-cpu/gpu-hybrid-inference-for-moe-models/SOSP25-chen.pdf)
- [CXL-Aware Memory Allocator for LLM Fine-Tuning](https://arxiv.org/html/2507.03305v2)
- [NVIDIA: CPU-GPU Memory Sharing for LLM Inference](https://developer.nvidia.com/blog/accelerate-large-scale-llm-inference-and-kv-cache-offload-with-cpu-gpu-memory-sharing/)

### Inter-VM Communication
- [ACRN Inter-VM Shared Memory (ivshmem)](https://projectacrn.github.io/latest/tutorials/enable_ivshmem.html)
- [DPDK Virtio-User for Container Networking](http://doc.dpdk.org/guides-25.11/howto/virtio_user_for_container_networking.html)
- [Shared-Memory Optimizations for Inter-VM Communication (ACM Survey)](https://dl.acm.org/doi/abs/10.1145/2847562)

### Community & Practice
- [Raft Visualization](https://thesecretlivesofdata.com/raft/) — Interactive Raft consensus visualization
- [Linux Insides](https://0xax.gitbooks.io/linux-insides/) — Free deep dive into Linux kernel internals
- [OSDev Wiki](https://wiki.osdev.org/) — Community resource for OS development

---

> **Final Word**: You're not just studying for a job. You're building a career as a systems architect who understands computing from the silicon up to the cloud. The Infrastructure Engineer role (Phase 1, months 1-6) is your entry point — it proves you can manage buildings at scale. The Systems Engineer role (Phase 2, months 7-18) is your destination — it proves you can design the buildings themselves, optimize them for specific tenants (LLM workloads), and measure every improvement with hard numbers.
>
> The Phase 2 projects aren't tutorials. They're the same caliber of work listed in Anthropic's actual JD: optimized microVMs, BPF schedulers, NUMA-aware memory allocators, shared-memory inter-VM communication, and eBPF observability. Each project produces a benchmark report with real performance data. The capstone integrates all five into a production platform you can demo live.
>
> Every project, every lab, every paper moves you closer to pouring your own foundation.
>
> Now break ground.
