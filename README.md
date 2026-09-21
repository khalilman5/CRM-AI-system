Odoo CRM AI Lead Assistant
An intelligent, privacy-first conversational assistant integrated directly into **Odoo CRM** (`crm.lead`). It allows sales teams and real estate agents to **create**, **update**, and **delete** leads using natural language—either through a native in-app chat widget or a headless terminal client.
Powered by local Large Language Models via **Ollama** (`qwen2.5:7b`), ensuring **100% data privacy**, zero external API costs, and instant on-premise execution.
---
## Key Features
- 💬 **Natural Language CRM Operations**: Perform complete lead management workflows by simply chatting in natural language (e.g., *"Add Omar, wants to buy a villa in Casablanca, high priority, phone 0612345678"*).
- 🏘️ **Real Estate Domain Awareness**: Automatically classifies operations (`buy`, `sell`, `rent`) and property types (`villa`, `house`, `apartment`), converting them into real Odoo CRM tags (`crm.tag`).
- ⚡ **Multi-Lead Batch Extraction**: Detects and extracts multiple distinct customers mentioned in a single prompt and creates all of them simultaneously.
- 🔄 **Conversational Slot-Filling & Clarification Queue**: If a message describes customer requirements without providing a name (the only mandatory field), the assistant remembers the extracted details and prompts specifically for the missing name.
- 🛡️ **Anti-Hallucination & Deterministic Execution**: The LLM never hallucinates record IDs or guesses database matches. Instead, it extracts search criteria, and real Odoo database queries handle the lookup and execution.
- 🖥️ **Dual Execution Modes**:
  - **Embedded Odoo Web Interface**: Native OWL chat interface with an animated typing indicator, accessible via a **"New Lead AI"** button on the CRM Leads list.
  - **Headless Terminal Client (`process.py`)**: Standalone interactive terminal runner communicating via XML-RPC for testing and automation outside the browser.
- 🔒 **100% Local & Private**: No customer contact details or notes leave your local infrastructure.
---
## 🏗️ Architecture & Workflow
```mermaid
flowchart TD
    subgraph UI_Layer ["Interface Layer"]
        A[Odoo Web UI: OWL Chat Widget]
        B[Terminal Client: process.py]
    end
    subgraph AI_Engine ["AI Operations System"]
        C[nodes.py: Intent & Entity Extraction]
        D[model.py: Ollama Local LLM]
        E[odoo_client.py: XML-RPC Client]
    end
    subgraph Odoo_Backend ["Odoo 17 / 18 / 19 Server"]
        F[crm.ai.lead.wizard: Transient Chat Session]
        G[(Odoo Database: crm.lead & crm.tag)]
    end
    A -->|Direct ORM env| F
    F -->|Verify & Parse| C
    B -->|Verify & Parse| C
    C <-->|Local Inference :11434| D
    C -->|ORM Queries| G
    B -->|XML-RPC API| E
    E -->|Remote Procedure Calls| G
