# Architecture

Le diagramme ci-dessous represente l'architecture actuelle du prototype et le
workflow de preparation d'un rendez-vous.

## Schema de principe

```mermaid
flowchart LR
   conseiller["Conseiller bancaire"] --> interface["Interface web\nSynthese client / RDV"]
   interface --> application["Application Flask\nOrchestration"]
   application --> analyse["Agent d'analyse\nProfil CSV + LangGraph"]
   donnees[("Donnees client\nCSV local")] --> analyse
   analyse --> foundry["Microsoft Foundry\nGeneration et synthese IA"]
   analyse --> execution["Execution Python\nCalcul des agregats"]
   execution --> analyse
   analyse --> resultat["Rapport de rendez-vous\nSujets et actions"]
   resultat --> interface
```

Ce schema resume le principe : l'application orchestre l'analyse des donnees
client, Foundry fournit les capacites IA, puis le resultat est restitue au
conseiller dans l'interface web.

## Vue technique

```mermaid
flowchart LR
    user["Conseiller bancaire"]
    browser["Navigateur web"]

    subgraph app["Application Python locale"]
        flask["Flask\nserver/app.py"]
        pages["Templates Jinja\nSynthese / RDV"]
        sse["API SSE\nPOST /api/rdv/workflow"]
        agent["CsvAnalysisAgent\nLangGraph"]
        profile["Profil CSV local\ncolonnes, types, valeurs manquantes"]
        tools["CsvTools"]
        generated["Programme Python genere\nprograms/<code_id>.py"]
        subprocess["Sous-processus Python\nexecution locale, 60 s"]
        artifacts["Artifacts d'execution\nprofile.json / aggregation.csv / report.json"]
        data["CSV clients\nstarter/data et inputs"]
    end

    subgraph azure["Azure"]
        foundry["Microsoft Foundry\nproject + deploiements LLM"]
    end

    user --> browser
    browser -->|GET pages| flask
    flask --> pages
    browser -->|POST + flux SSE| sse
    sse --> agent
    agent --> profile
    profile --> data
    agent --> tools
    tools -->|generation du code| foundry
    tools --> generated
    generated --> subprocess
    data --> subprocess
    subprocess --> artifacts
    artifacts -->|agregats valides| tools
    tools -->|synthese structuree| foundry
    agent -->|rapport + etapes| sse
    sse -->|evenements de progression| browser

    classDef local fill:#e8f0f7,stroke:#31627d,color:#102a43
    classDef azure fill:#e9f5ec,stroke:#2f7d4a,color:#12351f
    classDef planned fill:#f4f1e8,stroke:#8a6d3b,color:#4a391d,stroke-dasharray: 5 5
    class flask,pages,sse,agent,profile,tools,generated,subprocess,artifacts,data local
    class foundry,blob,cosmos,search azure
```

## Workflow de preparation du rendez-vous

1. Le navigateur ouvre la page client puis appelle l'endpoint SSE avec le
   client selectionne.
2. Flask charge le CSV du client et cree un repertoire d'execution dedie.
3. Le profil est calcule localement ; les lignes brutes ne sont pas envoyees a
   Foundry pour cette etape.
4. Foundry genere un programme Python a partir de l'objectif et du profil.
5. Le programme est valide, sauvegarde, puis execute localement sur le CSV
   normalise.
6. Les agregats produits sont valides avant d'etre envoyes a Foundry pour la
   synthese structuree.
7. Le rapport et les etapes suggerees sont renvoyes au navigateur via SSE.

Les ressources Blob Storage, Cosmos DB et Azure AI Search sont bien creees par
`infra/main.bicep`, mais ne sont pas encore utilisees par le workflow de
`starter`.