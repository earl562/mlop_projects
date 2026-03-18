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

> You've managed buildings. Now you're going to design the structural systems themselves.

#### Project 2.1: "The Foundation" — xv6 Operating System Labs

**Real Estate Analogy**: Study soil science before you pour any foundation

**What You'll Build**:
- Complete MIT 6.1810 labs on the xv6 operating system
- Focus areas: page tables, traps, system calls, scheduling, file system

**Skills Practiced**:
- Kernel programming in C
- Virtual memory management (the master floorplan)
- Process isolation at the kernel level
- Interrupt handling (the fire alarm system)

**Acceptance Criteria**:
- [ ] All 6.1810 labs passing
- [ ] Can explain: "How does xv6 isolate process memory using page tables?"
- [ ] Can explain: "What happens during a trap from user to kernel mode?"
- [ ] Written reflection on how xv6 concepts map to real sandboxing

---

#### Project 2.2: "The Custom Foundation" — Build a Hypervisor

**Real Estate Analogy**: Design a new type of foundation that supports multiple independent buildings on one lot

**What You'll Build**:
- A minimal Type-2 hypervisor using KVM (Linux's built-in virtualization)
- Boot a guest Linux kernel in a VM you created from scratch
- Implement basic device emulation (serial console, block device)
- Written in C or Rust

**Reference**: Study Firecracker's source code (50,000 lines of Rust) and kvmtool

**Skills Practiced**:
- KVM API (`/dev/kvm` ioctl interface)
- x86 virtualization extensions (VT-x: VMCS, VMX, EPT)
- Virtual device models (virtio)
- Memory mapping for guest physical → host virtual translation
- Rust systems programming (if you choose Rust)

**Acceptance Criteria**:
- [ ] Guest Linux kernel boots to userspace in your hypervisor
- [ ] Serial console I/O works (you can type commands in the guest)
- [ ] Memory isolation verified (guest can't access host memory)
- [ ] Boot time measured and documented
- [ ] Architecture document explaining your design decisions

---

#### Project 2.3: "The Prefab Factory" — Firecracker microVM Sandbox

**Real Estate Analogy**: Build a factory that mass-produces prefab modular homes in under 200ms each

**What You'll Build**:
- Deploy Firecracker on a bare-metal or nested-virt machine
- Build an orchestration layer that:
  - Spins up microVMs on demand via Firecracker's REST API
  - Injects user code into the microVM
  - Captures output and returns results
  - Destroys the microVM after execution
- Optimize for cold-start latency (target: <200ms)
- Implement snapshot/restore for "warm" starts

**Skills Practiced**:
- Firecracker microVM management
- KVM-based virtualization in practice
- Performance optimization (cold start, memory overhead)
- The jailer security model (chroot + cgroups + seccomp)
- REST API design for VM lifecycle management

**Acceptance Criteria**:
- [ ] microVMs boot in <200ms
- [ ] Code execution works end-to-end (submit code → get output)
- [ ] Jailer is configured with full security (cgroups, seccomp, chroot)
- [ ] Snapshot/restore reduces warm-start to <50ms
- [ ] Memory overhead per microVM documented (<5MB target)
- [ ] Comparison doc: "Firecracker microVM vs Docker container vs full VM"

---

#### Project 2.4: "The Smart Building" — Kernel Performance Optimization

**Real Estate Analogy**: Retrofit a building with smart systems — IoT sensors, predictive HVAC, optimized elevator scheduling

**What You'll Build**:
- Take the Firecracker sandbox from Project 2.3 and optimize it for ML inference workloads:
  - Kernel parameter tuning (scheduler, memory, networking)
  - Custom cgroup configurations for GPU/CPU-intensive workloads
  - eBPF-based monitoring and performance analysis
  - NUMA-aware memory allocation
- Benchmark before and after each optimization

**Skills Practiced**:
- Linux kernel tuning (sysctl, boot parameters)
- eBPF programming (the smart building sensor network)
- perf profiling and flame graphs
- NUMA topology and memory placement
- Performance benchmarking methodology

**Acceptance Criteria**:
- [ ] Baseline benchmarks documented (latency, throughput, memory)
- [ ] At least 3 kernel optimizations implemented with measured impact
- [ ] eBPF program monitors sandbox syscall patterns
- [ ] Flame graph analysis identifies top bottlenecks
- [ ] Final report: "Optimizing microVM Performance for ML Inference"

---

#### Project 2.5: "The Development" — Production Sandbox Platform

**Real Estate Analogy**: Build an entire mixed-use development — the capstone that combines everything

**What You'll Build**:
- A production-grade sandbox execution platform combining ALL prior work:
  - **Frontend**: API accepting code execution requests
  - **Orchestrator**: Distributes work across a pool of machines
  - **Executor**: Firecracker microVMs with optimized kernel configs
  - **Isolation**: Full security stack (namespaces, cgroups, seccomp, KVM)
  - **Observability**: Prometheus, Grafana, eBPF-based tracing
  - **IaC**: Entire stack deployable via Terraform

**Skills Practiced**:
- Everything from Phase 1 and Phase 2 integrated
- System design and architecture decisions
- Production readiness (graceful degradation, circuit breakers, rate limiting)
- Documentation and operational runbooks

**This is your portfolio piece.** This is what you walk into the Anthropic interview with.

**Acceptance Criteria**:
- [ ] End-to-end: submit code via API → execute in microVM → get results
- [ ] Handles 100+ concurrent sandbox executions
- [ ] Security audit: no container/VM escapes in threat model
- [ ] Full observability dashboard
- [ ] Operational runbook for common failure modes
- [ ] Architecture document suitable for a system design interview
- [ ] Public GitHub repo with clean README

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

### Phase 2 Milestones (Months 7-12): Architect's License

```
Month 7-8: Soil Science & Structural Engineering
├── [ ] Project 2.1 complete (xv6 labs — all passing)
├── [ ] Project 2.2 started (minimal hypervisor with KVM)
├── [ ] Start MIT 6.172 (Performance Engineering) — first 6 lectures
├── [ ] Read: "Linux Kernel Development" by Robert Love (3rd Edition)
└── [ ] Can explain: "How does KVM create a virtual machine at the hardware level?"

Month 9-10: Advanced Construction
├── [ ] Project 2.2 complete (minimal hypervisor boots Linux)
├── [ ] Project 2.3 complete (Firecracker microVM sandbox)
├── [ ] MIT 6.172 — lectures 7-14, complete 2+ homework assignments
├── [ ] Read Firecracker paper: "Firecracker: Lightweight Virtualization for Serverless Applications"
└── [ ] Can explain: "What's the difference between KVM, QEMU, and Firecracker?"

Month 11-12: Capstone & Portfolio
├── [ ] Project 2.4 complete (kernel performance optimization)
├── [ ] Project 2.5 complete (production sandbox platform)
├── [ ] MIT 6.172 — final project (Leiserchess)
├── [ ] Architecture document for Project 2.5 polished for interviews
├── [ ] CHECKPOINT: Could you pass a Systems Software Engineer interview? Practice.
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
| *Understanding the Linux Kernel* — Bovet & Cesati | The deep geology survey | Deep reference |
| *Computer Systems: A Programmer's Perspective* (CS:APP) — Bryant & O'Hallaron | The materials science textbook | Must-read for perf |
| *Operating Systems: Three Easy Pieces* (OSTEP) — Arpaci-Dusseau | The accessible intro to soil science | Great companion to 6.1810 |
| *Programming Rust* — Blandy, Orendorff, Tindall | Modern engineered materials handbook | When you're ready for Rust |

#### Key Papers
| Paper | Why It Matters |
|---|---|
| *Firecracker: Lightweight Virtualization for Serverless Applications* (NSDI '20) | This IS the technology Anthropic builds on |
| *Raft: In Search of an Understandable Consensus Protocol* | Core distributed systems — you'll implement this in 6.5840 |
| *gVisor: Container Security Through Kernel Reimplementation* | Google's approach to sandboxing — alternative to Firecracker |
| *The Google File System* | Foundational distributed storage paper |
| *Bubblewrap: Unprivileged Sandboxing Tool* | Used by Anthropic's sandbox-runtime on Linux |

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

### Community & Practice
- [Raft Visualization](https://thesecretlivesofdata.com/raft/) — Interactive Raft consensus visualization
- [Linux Insides](https://0xax.gitbooks.io/linux-insides/) — Free deep dive into Linux kernel internals
- [OSDev Wiki](https://wiki.osdev.org/) — Community resource for OS development

---

> **Final Word**: You're not just studying for a job. You're building a career as a systems architect who understands computing from the silicon up to the cloud. The Infrastructure Engineer role is your entry point — it proves you can manage buildings at scale. The Systems Engineer role is your destination — it proves you can design the buildings themselves. Every project, every lab, every paper moves you closer to pouring your own foundation.
>
> Now break ground.
