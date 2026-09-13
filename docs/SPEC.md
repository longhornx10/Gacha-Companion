You are building a production-quality local-first application named:

    Gacha Companion

This is NOT a one-off Zenless Zone Zero chatbot.

The goal is to build a reusable framework for persistent, account-aware Gacha Companions for games with character rosters, builds, equipment, gear, teams, progression, resources, endgame encounters, and changing online information.

Zenless Zone Zero (ZZZ) is the FIRST complete reference implementation.

Future games must include at minimum:
- Honkai: Star Rail (HSR)
- Neverness to Everness (NTE)
- additional similar games later

The architecture MUST therefore be game-agnostic at its core.

Do not bake ZZZ terminology, team sizes, equipment types, gear slots, resource names, stat names, or endgame rules directly into the core application.

ZZZ-specific concepts belong inside a ZZZ game adapter/plugin.

==================================================
PRIMARY PRODUCT GOAL
==================================================

The user wants a persistent Gacha Companion that can:

- speak with a configurable personality/persona;
- remember the user's actual game account and builds;
- inspect screenshots;
- research current game information;
- cross-check information across multiple sources;
- provide account-aware team/build advice;
- tutor combat mechanics in very simple terms;
- provide step-by-step and button-by-button rotations;
- track gear, inventory and upgrade resources;
- evaluate gear quality;
- recommend farming/upgrade priorities;
- optimize multiple mutually exclusive teams for endgame modes;
- record combat results and player weaknesses;
- maintain a long-term training profile;
- detect changes in online information over time;
- maintain local, inspectable, exportable data;
- eventually support multiple games from the same application.

The most important architectural rule is:

    THE LLM IS NOT THE DATABASE.

The LLM is responsible for:
- conversation;
- persona;
- explanation;
- reasoning;
- research coordination;
- interpreting screenshots;
- extracting proposed structured information;
- presenting recommendations.

Deterministic application code/database logic is responsible for:
- roster state;
- builds;
- equipment;
- gear;
- resources;
- team membership;
- calculations;
- history;
- codes;
- progression;
- saved preferences;
- scoring components;
- resource thresholds;
- user-confirmed updates.

Do not rely on chat history or fuzzy LLM memory as the authoritative state.

==================================================
CURRENT ENVIRONMENT / INFERENCE
==================================================

The companion will initially be used through Open WebUI Desktop on Linux.

The user has access to an OpenAI-compatible remote inference endpoint.

External base URL:

    https://llm.tictac.one/v1

Do NOT hardcode credentials.

All API credentials must come from environment variables or local configuration excluded from git.

Primary multimodal model:

    muse-glimmer-30b-vlm-128k

This model supports:
- text input;
- image input;
- 128K context;
- OpenAI-compatible chat completions.

The existing infrastructure can already accept OpenAI-style image_url content.

The application should NOT depend specifically on this model.

LLM providers/models must be configurable through an abstraction so Glimmer can later be replaced with Qwen, DeepSeek, another VLM, etc.

Suggested environment variables:

    GAME_COMPANION_LLM_BASE_URL
    GAME_COMPANION_LLM_API_KEY
    GAME_COMPANION_LLM_MODEL
    GAME_COMPANION_DATA_DIR

Never commit or log API keys.

==================================================
TECHNICAL DIRECTION
==================================================

Use Python unless there is a compelling reason not to.

Preferred baseline:

- Python 3.12+
- FastAPI for local service/API
- Pydantic for typed schemas
- SQLite for authoritative local storage
- SQLAlchemy 2.x or equivalent mature ORM/data layer
- Alembic or another proper migration mechanism
- pytest
- structured logging
- HTTP client abstraction for LLM/search integrations
- JSON + Markdown export capability
- clean pyproject.toml
- type hints throughout

The application should be easy to run locally on Linux.

Prefer:

    game-companion serve

or an equivalent simple launcher.

Default local service binding should be localhost only unless explicitly configured otherwise.

Example:

    http://127.0.0.1:8765

Do not expose the service to the LAN by default.

==================================================
REPOSITORY STRUCTURE
==================================================

Use approximately this separation of concerns.

Exact filenames may change if there is a cleaner implementation.

game-companion/
    pyproject.toml
    README.md
    .env.example

    game_companion/
        app.py
        config.py
        logging.py

        api/
            routes/
            schemas/

        core/
            games/
            roster/
            equipment/
            gear/
            teams/
            encounters/
            resources/
            research/
            coaching/
            history/
            codes/
            vision/
            recommendations/
            llm/

        db/
            models/
            repositories/
            migrations/

        games/
            zzz/
                manifest.*
                adapter.py
                schemas.py
                terminology.py
                sources.py
                team_rules.py
                gear_rules.py
                resource_rules.py
                screenshot_schemas.py
                prompts/
                tests/

            example_game/
                ...

        integrations/
            openwebui/
            llm/
            search/

        exports/

    tests/
        unit/
        integration/
        game_adapter_contract/

    docs/
        architecture.md
        game-adapter.md
        data-model.md
        openwebui.md
        zzz.md

==================================================
CORE DOMAIN MODEL
==================================================

The core should understand generic concepts such as:

Game
PlayerProfile
PlayerPreference
Character
CharacterProgress
CharacterBuild
Skill
EquipmentItem
GearItem
GearSet
Stat
Resource
ResourceRequirement
Team
TeamMember
Encounter
EncounterSlot
CombatResult
TrainingIssue
TrainingGoal
Recommendation
RedeemCode
ResearchSource
ResearchClaim
SourceEvidence
ChangeRecord
ScreenshotImport
AuditResult

Do not name core tables/classes:

DriveDisc
WEngine
Mindscape
DeadlyAssault

unless they are inside games/zzz/.

Instead, generic core concepts map through the game adapter.

Example ZZZ mappings:

Character -> Agent
Equipment -> W-Engine
GearItem -> Drive Disc
CharacterDuplicationLevel -> Mindscape
CharacterSpecialProgress -> Core Skill
Team size -> 3

Example future HSR mappings:

Character -> Character
Equipment -> Light Cone
GearItem -> Relic / Planar Ornament
Team size -> 4
Duplication -> Eidolon

The core API should be able to ask the active GameAdapter how a generic concept maps to a particular game.

==================================================
GAME ADAPTER / PLUGIN CONTRACT
==================================================

Create a formal GameAdapter interface/protocol.

A game adapter should be responsible for supplying things such as:

- game ID;
- display name;
- terminology;
- character terminology;
- equipment terminology;
- gear terminology;
- gear slots;
- stat definitions;
- team-size constraints;
- endgame encounter constraints;
- resource categories;
- progression rules;
- gear evaluation hooks;
- team compatibility hooks;
- source registry;
- screenshot extraction schemas;
- game-specific validation;
- game-specific prompts;
- redeem-code discovery configuration;
- game-specific recommendation/scoring components.

Adding another game should NOT require modifying core business logic unless a genuinely new generic capability is discovered.

To prove this architecture works, include a tiny fake/example second game adapter in tests.

The adapter-contract test MUST demonstrate that core functionality does not assume:

- exactly 3 characters per team;
- Drive Discs;
- W-Engines;
- Mindscapes;
- ZZZ stat names;
- ZZZ resources;
- ZZZ endgame modes.

==================================================
DATA OWNERSHIP / USER SCOPING
==================================================

All player data must be associated with:

    game_id
    player_profile_id

Even if only one user exists initially.

Global preferences may exist separately from game-specific preferences.

Examples of global preferences:

- prefers simple rotations;
- wants button-by-button explanations;
- dislikes high-execution teams;
- values comfort over theoretical maximum DPS;
- preferred explanation detail;
- preferred personas.

Examples of game-specific state:

- owned characters;
- builds;
- equipment;
- gear;
- resources;
- teams;
- clears;
- goals.

==================================================
PERSONA SYSTEM
==================================================

Persona must be separate from game state.

The user must be able to create configurable personalities such as:

    ZZZ + Nicole-style persona
    ZZZ + Anby-style persona
    HSR + March-style persona

Switching personas MUST NOT create another copy of the player's game database.

Persona should influence:

- tone;
- mannerisms;
- phrasing;
- humor;
- verbosity;
- tutoring style.

Persona must NOT alter:

- stored account facts;
- calculations;
- citations;
- source trust;
- validation;
- deterministic results.

Create a persona configuration schema.

Support user-created personas through local config/data.

==================================================
MILESTONE 1
FOUNDATION
==================================================

Implement this first.

Create:

- project structure;
- config;
- database;
- migrations;
- repository/data layer;
- FastAPI service;
- health endpoint;
- game registry;
- GameAdapter contract;
- ZZZ adapter skeleton;
- fake second adapter for contract testing;
- player profile;
- character records;
- builds;
- equipment;
- gear;
- resources;
- teams;
- history;
- preferences;
- codes;
- source metadata;
- change history.

Implement CRUD operations.

Implement JSON export.

Implement human-readable Markdown export.

Exports should allow the user to inspect their data without requiring the program.

SQLite remains authoritative.

Add automated tests before moving onward.

==================================================
MILESTONE 2
ZZZ ACCOUNT MODEL
==================================================

Implement the first complete ZZZ data model.

Track per Agent:

- ownership;
- level;
- relevant base/current stats;
- Mindscape;
- Core Skill level;
- Basic Attack level;
- Dodge level;
- Assist level;
- Special Attack level;
- Chain Attack level;
- current W-Engine;
- W-Engine level;
- W-Engine star/refinement level;
- Drive Disc loadout;
- 4pc set;
- 2pc set;
- individual Drive Disc references;
- user notes;
- favorite status;
- progression goals.

For individual Drive Discs, support:

- unique local ID;
- set;
- slot;
- main stat;
- main-stat value where relevant;
- substats;
- substat values;
- roll information where known;
- level;
- locked/favorited state;
- equipped character;
- notes;
- source of entry;
- last verified timestamp.

Do not require every field.

Support partial records.

==================================================
MILESTONE 3
OPEN WEBUI INTEGRATION
==================================================

Create an Open WebUI-compatible tool/integration.

The Open WebUI layer should be thin.

Do not put business logic into the Open WebUI wrapper.

It should call the local Gacha Companion service.

Expose tools conceptually similar to:

    get_player_profile
    get_character
    list_characters
    update_character
    get_build
    update_build

    list_equipment
    get_equipment

    list_gear
    get_gear
    add_gear
    update_gear
    favorite_gear

    get_resources
    update_resource

    list_teams
    save_team

    search_game_sources

    get_active_codes
    mark_code_used

    record_combat_result
    get_combat_history

    record_training_issue
    get_training_focus

Tool descriptions must make it clear to the model when to call them.

Account-specific questions should retrieve authoritative state before answering.

Example:

User:
    Who can my Burnice partner with?

The LLM should be encouraged to retrieve:

    get_character("Burnice")
    list_characters(...)
    possibly saved teams

before making recommendations.

==================================================
MILESTONE 4
LLM ABSTRACTION
==================================================

Implement an OpenAI-compatible LLM provider abstraction.

Support:

- base URL;
- API key;
- model;
- timeout;
- optional image content;
- text completions;
- structured extraction requests.

Primary target initially:

    muse-glimmer-30b-vlm-128k

Do not couple domain logic to the provider.

No API key should appear in logs.

==================================================
MILESTONE 5
SCREENSHOT / VISION INGESTION
==================================================

Implement screenshot-assisted data entry.

The workflow MUST be:

    screenshot
        ->
    VLM extraction
        ->
    typed candidate object
        ->
    schema validation
        ->
    show proposed changes
        ->
    explicit user confirmation
        ->
    authoritative database update

Never allow raw VLM output to silently overwrite account data.

Track:

- import timestamp;
- source screenshot filename/hash if useful;
- extraction confidence where available;
- fields extracted;
- fields rejected;
- user-confirmed changes.

Start with ZZZ character/build screens.

Design extraction schemas for:

- Agent overview;
- skills;
- W-Engine;
- Drive Disc;
- Drive Disc detail;
- resources/inventory where feasible.

If a value cannot be confidently determined, leave it unknown.

DO NOT guess.

==================================================
MILESTONE 6
WEB RESEARCH / SOURCE SYSTEM
==================================================

Build a game-agnostic research layer.

Each game adapter supplies a source registry.

For ZZZ, support source categories such as:

- official;
- official announcements/patch notes;
- mechanics/reference databases;
- established build resources;
- maintained wikis/databases;
- community discussion.

The system must track:

- source URL;
- source name;
- category;
- trust/priority;
- access timestamp;
- publication/update timestamp if known;
- claims derived from it;
- citations/evidence.

Patch-sensitive advice should prefer current information.

Important mechanics/build claims should be cross-checked against at least two independent sources when practical.

Do not pretend consensus exists if sources disagree.

Differentiate:

    official fact
    established mechanics claim
    build recommendation
    community consensus
    speculation

Do not let the LLM cite only search snippets as though it read a source.

Provide an abstraction that can later use:

- Open WebUI web search;
- SearXNG;
- another provider.

Do not tightly couple search logic to one engine.

==================================================
MILESTONE 7
COMBAT TUTOR
==================================================

Implement a tutoring mode for ZZZ.

It should support:

- explain one Agent's kit;
- assume little prior mechanic knowledge;
- avoid unexplained jargon;
- explain why abilities matter;
- explain resource generation/spending;
- basic rotation;
- advanced rotation;
- button-by-button rotation;
- team rotation;
- substitute-aware rotation.

Player preferences should affect explanations.

For example:

    simple_mode = true
    prefers_button_by_button = true
    dislikes_frame_tight_sequences = true

These preferences should persist.

==================================================
MILESTONE 8
#CODES
==================================================

Implement redeem-code tracking.

The user wants:

    #CODES

to produce known active codes for the current game/version.

Track:

- code;
- game;
- discovered date;
- expiration date if known;
- active/expired/unknown status;
- source;
- whether the current player marked it used;
- possible recycled/reactivated status.

Used codes should render as strikethrough in human-facing output.

Do NOT permanently suppress a used code if reliable sources indicate it was reactivated/recycled.

==================================================
MILESTONE 9
ACCOUNT-AWARE TEAM RECOMMENDATIONS
==================================================

Implement initial account-aware team building.

Use:

- actual owned roster;
- actual builds where relevant;
- current equipment;
- saved user preferences;
- current online recommendations;
- encounter needs.

Return several categories when useful:

    best theoretical team
    best team from user's roster
    easiest/most comfortable team
    substitute options
    lower-execution option

If a team is difficult, explain why.

If substitutions reduce performance, explain the tradeoff.

Do not manufacture precise DPS percentages yet.

==================================================
MILESTONE 10
W-ENGINE / EQUIPMENT COMPARISON
==================================================

Implement generic equipment comparison with ZZZ rules.

Support:

- owned A-rank+ W-Engines;
- signature W-Engine;
- best-in-slot;
- alternatives;
- star/refinement;
- character compatibility;
- relative recommendation;
- source evidence.

Account-aware comparisons must distinguish:

    theoretical best
    best owned
    easiest upgrade
    best use of limited equipment shared among characters

==================================================
MILESTONE 11
DRIVE DISC INVENTORY / VALUE
==================================================

Implement Drive Disc storage and evaluation.

The user wants to determine:

- which discs are strong;
- which characters could use them;
- which substats matter;
- which are safe to discard;
- which are niche but valuable;
- which should be favorited.

Make gear evaluation generic in the core.

The ZZZ adapter supplies:

- useful sets;
- slots;
- stat rules;
- character/build archetypes;
- scoring hooks.

A gear evaluation should explain its reasoning.

Do NOT reduce all evaluation to one opaque LLM-generated score.

Useful output might include:

    strong
    useful
    niche
    speculative/future-use
    weak
    likely-safe-to-discard

Also expose contributing reasons.

==================================================
MILESTONE 12
RESOURCE TRACKING
==================================================

Track general progression resources.

ZZZ examples include:

- Agent ascension materials;
- Agent EXP;
- W-Engine EXP;
- Drive EXP;
- Tactical/skill materials;
- Core Skill materials;
- Expert Challenge items;
- other relevant upgrade resources.

Implement resource-state rules deterministically.

For the user's requested resource semantics:

Suppose one character requires a full amount X of a material to reach the respective max target, and current planned characters collectively require Y.

The requested concepts include:

    CRITICALLY LOW / RED
    VERY LOW / ORANGE
    DONE / WHITE
    PREP / CYAN OR LIME

Do not leave this entirely to the LLM.

Model these thresholds through game/resource rules.

Because the exact interpretation can have edge cases, make threshold logic:

- tested;
- documented;
- configurable;
- explainable.

Return both:

    status
    calculation/explanation

==================================================
MILESTONE 13
UPGRADE / FARMING PLANNER
==================================================

Implement an account-wide progression recommendation system.

It should be able to answer:

    What should I farm next?
    Which Agent skill should I level next?
    Who benefits most from today's resources?
    Should I farm Drive Discs or skill materials?
    Which upgrade gives my useful teams the greatest benefit?

Consider:

- active teams;
- planned teams;
- Agent progression;
- skill progression;
- W-Engines;
- gear/build quality;
- current inventory;
- resource cost;
- farming availability;
- user goals.

Do not pretend to know exact performance gain if insufficient data exists.

Return a prioritized plan with reasons.

==================================================
MILESTONE 14
ROSTER HEALTH / AUDIT
==================================================

Implement an audit system.

For each owned character:

- compare stored build against current strong build patterns;
- inspect level/progression;
- inspect skill levels;
- inspect equipment;
- inspect gear;
- identify obvious shortcomings;
- identify suspicious/outdated stored data;
- identify last verified timestamp.

Support:

    verify my roster

and:

    audit Burnice

The system should also support manually verifying stored state against new screenshots.

==================================================
MILESTONE 15
MULTI-TEAM OPTIMIZER
==================================================

This is one of the hardest requirements.

Build it AFTER the structured account model exists.

The core optimizer must be generic.

Do NOT implement only:

    optimize_deadly_assault()

Instead create something conceptually like:

    optimize_team_allocation(
        roster,
        encounters,
        game_rules,
        objective,
        constraints,
        player_preferences,
    )

ZZZ adapters then provide Deadly Assault / Shiyu rules.

The key problem:

A character cannot exist on multiple simultaneous teams.

The optimizer must account for the opportunity cost of assigning a powerful support/Agent to one team instead of another.

Potential objectives:

    maximize total expected effectiveness
    maximize number of likely full-clear encounters
    maximize expected stars
    prioritize first two encounters and accept a weaker third
    maximize comfort
    minimize execution difficulty

The user's desired scenario includes cases like:

    Team 1 with Agent X = 100
    Team 2 without Agent X = 60

but reallocating Agent X might produce:

    Team 1 = 85
    Team 2 = 100
    Team 3 = 95

The optimizer should recognize that the second allocation may be globally better.

Do NOT fabricate exact percentages.

Create an explainable scoring framework.

==================================================
MILESTONE 16
TEAM SCORING
==================================================

The user ultimately wants concepts such as:

    Theoretical MAX DPS
    Overall Team Viability 1-10
    Relative Combat Effectiveness %

These numbers must NOT be hallucinated.

Design scoring components.

Possible components include:

- character synergy;
- role coverage;
- encounter matchup;
- build readiness;
- equipment quality;
- gear quality;
- execution difficulty;
- player comfort;
- current source consensus;
- actual historical user results.

Keep individual components visible.

If a value is heuristic, label it HEURISTIC.

If no real DPS simulation exists, do not label a heuristic score as literal DPS.

Create enough structure that a real simulator or better quantitative model can be added later.

==================================================
MILESTONE 17
COMBAT RESULTS / VICTORY HISTORY
==================================================

Track user performance over time.

Store:

- game;
- game mode;
- encounter;
- date;
- team;
- character builds or build snapshot references;
- score;
- stars/rank;
- clear/fail;
- clear time if applicable;
- retries;
- user notes;
- perceived difficulty.

Allow trends such as:

    win rate
    average clear performance
    performance by team
    performance by encounter
    improvement over time

Do not mutate past results if current builds change.

Reference snapshots/history where appropriate.

==================================================
MILESTONE 18
PERSONAL TRAINING MODEL
==================================================

Track player weaknesses.

Examples:

- rotation mistakes;
- swap timing;
- defensive assist timing;
- resource overcap;
- failure to maintain a buff;
- poor uptime;
- difficult execution sequence;
- repeated deaths at the same phase;
- misunderstanding a kit;
- team too mechanically demanding.

Allow the companion to maintain:

    training issues
    training goals
    progress
    resolved issues
    recurring issues

Future tutoring should retrieve relevant training history.

Example:

If the player repeatedly struggles with a particular swap sequence, future rotation explanations should adapt and either:

- teach that sequence more carefully;
- offer a simpler alternative;
- recommend a lower-execution team.

==================================================
MILESTONE 19
DAILY CHANGE / DATA AUDIT
==================================================

Implement a change-monitoring framework.

Do not blindly overwrite stored game/reference data.

The system should periodically be able to:

- fetch important trusted sources;
- compare current information with previously known information;
- detect meaningful changes;
- identify new characters/equipment;
- identify patch changes;
- identify build recommendation changes;
- flag source disagreements;
- generate a daily/periodic changelog.

Maintain historical records.

Use change records such as:

    detected_at
    game
    entity
    previous_value
    proposed_value
    source
    evidence
    confidence
    review_status

For important canonical-data changes, prefer:

    detect -> report -> review/confirm -> update

rather than silent mutation.

==================================================
LOCAL FILES / EXPORTS
==================================================

The user explicitly wants quickly referenceable local files.

Create useful export formats.

Examples:

    exports/zzz/roster.md
    exports/zzz/roster.json
    exports/zzz/resources.md
    exports/zzz/teams.md
    exports/zzz/training.md
    exports/zzz/history/
    exports/zzz/changelog/

Do not make these the primary writable database.

SQLite is authoritative.

Exports should be regenerable.

==================================================
AUDIT / HISTORY
==================================================

Important state should include timestamps such as:

    created_at
    updated_at
    last_verified_at

Where useful, preserve previous values.

Particularly important for:

- builds;
- equipment;
- gear ownership;
- resources;
- source-derived facts;
- character progression.

We want to be able to answer:

    When did this change?
    Where did this information come from?
    Was this entered manually, from screenshot extraction, or imported?
    When was it last verified?

==================================================
SAFETY / DATA INTEGRITY
==================================================

Never silently overwrite good structured data based solely on uncertain LLM output.

For uncertain imports/research:

    candidate
        ->
    validate
        ->
    diff
        ->
    confirm
        ->
    commit

Database writes should use transactions.

Use foreign keys.

Use migrations.

Add uniqueness constraints where appropriate.

Do not create an unmaintainable giant JSON blob for all game state.

Flexible JSON columns may be used where they make sense, but important searchable state should have structured schemas.

==================================================
TESTING REQUIREMENTS
==================================================

Tests are not optional.

At minimum create tests for:

- migrations;
- CRUD;
- game-adapter contract;
- ZZZ adapter mappings;
- fake second-game adapter;
- roster state;
- build state;
- gear;
- resources;
- codes;
- exports;
- team allocation constraints;
- duplicate character prevention across simultaneous teams;
- resource-state thresholds;
- screenshot candidate validation;
- LLM structured-output validation;
- account isolation;
- game isolation;
- source metadata/history.

No real paid/external API calls should be required for the normal test suite.

Use fixtures/mocks.

Create optional integration tests for the configured Planck endpoint.

==================================================
DOCUMENTATION REQUIREMENTS
==================================================

Create documentation that explains:

1. architecture;
2. how state is stored;
3. how to run locally;
4. environment variables;
5. how Open WebUI connects;
6. how to add a new game;
7. how to add a persona;
8. how screenshot ingestion works;
9. how research/source trust works;
10. how scoring works;
11. how backups/exports work.

The new-game guide must be good enough that someone can add HSR later without reverse engineering the codebase.

==================================================
IMPLEMENTATION ORDER
==================================================

Work in dependency order.

Prioritize:

Foundation
-> generic game plugin architecture
-> ZZZ structured account state
-> Open WebUI integration
-> LLM provider abstraction
-> persona
-> screenshot ingestion
-> research
-> tutoring
-> codes
-> account-aware team recommendations
-> equipment/W-Engine analysis
-> Drive Disc inventory/evaluation
-> resources
-> farming/upgrade planner
-> roster audit
-> multi-team optimizer
-> scoring
-> combat history
-> training system
-> daily audits

Do NOT begin with the most complicated optimizer.

Build the authoritative data model first.

==================================================
WORKING STYLE
==================================================

Work directly in the repository.

Inspect before changing.

Prefer clear, maintainable modules over giant files.

Keep domain logic out of route handlers.

Keep Open WebUI-specific logic out of the core.

Keep ZZZ-specific logic out of the core.

Do not hardcode secrets.

Do not fake functionality.

If a feature cannot yet be completed accurately because required source data/scoring data does not exist, implement:

- the interface;
- the data structures;
- validation;
- tests;
- a clearly documented placeholder;

rather than fabricating numbers.

Do not claim a feature works until tests/verification demonstrate it.

Use the smallest sensible dependency set.

Avoid unnecessary infrastructure.

This should remain practical for one Linux desktop user with SQLite.

Do not add Redis, PostgreSQL, Kubernetes, message queues, or distributed infrastructure unless a demonstrated requirement appears later.

==================================================
ACCEPTANCE CRITERIA FOR FIRST USEFUL RELEASE
==================================================

Before calling the first useful release complete, a user should be able to:

1. start Gacha Companion locally;

2. connect Open WebUI to its tool interface;

3. select ZZZ;

4. select/configure a persona;

5. create their player profile;

6. add several Agents;

7. save Burnice's:
   - Mindscape;
   - levels;
   - W-Engine;
   - skills;
   - Drive Disc setup;

8. start a completely new conversation and ask:

       "What is my Burnice running?"

   and receive the authoritative stored build;

9. ask:

       "Who should my Burnice partner with?"

   and have the system retrieve:
   - Burnice;
   - owned roster;
   - current research as needed;

10. receive account-aware advice;

11. upload a build screenshot and receive a proposed structured update that requires confirmation before saving;

12. run:

       #CODES

   and see tracked active/used codes;

13. export their current ZZZ account to readable Markdown/JSON;

14. restart the program and retain all state.

==================================================
SECOND ACCEPTANCE MILESTONE
==================================================

The next release should additionally support:

- individual Drive Disc storage;
- screenshot-assisted Drive Disc entry;
- W-Engine inventory;
- Drive Disc usefulness evaluation;
- resource inventory;
- deterministic resource warning states;
- progression/farming priorities;
- roster build audit;
- basic combat result history.

==================================================
THIRD ACCEPTANCE MILESTONE
==================================================

The advanced milestone should support:

- Deadly Assault / multi-team allocation;
- mutually exclusive Agent assignment;
- explainable heuristic team scoring;
- encounter-specific recommendations;
- adaptive team alternatives;
- player comfort/execution weighting;
- training-issue tracking;
- performance history;
- periodic source/change audit.

==================================================
IMPORTANT PRODUCT PRINCIPLE
==================================================

The finished experience should feel like:

    "This companion knows MY account."

not:

    "This chatbot knows facts about ZZZ."

When asked:

    "Who should Burnice partner with?"

it should know which Burnice the user owns, how she is built, what teammates are owned, which teammates are already committed elsewhere, what the user finds difficult to play, and what current sources say.

When the user changes something, the system should update that structured state.

When another persona is selected, the same underlying account state remains available.

When another game is selected, that game's state remains isolated but the same companion framework is reused.

==================================================
FIRST TASK
==================================================

Start by:

1. inspect the repository/environment;
2. write docs/architecture.md describing the proposed implementation;
3. define the GameAdapter interface;
4. define the database/domain model;
5. create the application skeleton;
6. implement migrations;
7. implement the fake second-game adapter;
8. implement the initial ZZZ adapter;
9. implement tests proving that game-specific assumptions do not leak into core;
10. proceed into the first useful-release milestones without waiting for further instruction unless genuinely blocked.

Keep a TODO/milestone document updated as work progresses.

If you encounter ambiguity, make the smallest reversible architectural decision that preserves extensibility, document it, and continue.

Do not stop merely because every advanced feature cannot be perfected in one pass.

Get the foundation correct, then implement as much of the dependency-ordered roadmap as can be completed and verified.