# for testing
import pytest
from httpx import AsyncClient, ASGITransport
import json

# db connectivity
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

from app.main import app        # the app itself
from app.database import get_db # to get database session for every FastAPI route
from app.models import metadata # metadata knows all my tables

# seeds
from app.seed_furniture import seed as seed_furniture
from app.seed_quickpicks import seed as seed_quickpicks
from app.seed_scenarios import seed as seed_scenarios
from app.seed_users import seed as seed_users
# Connection URL
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

# Engine to make and test db connection
engine = create_async_engine(TEST_DATABASE_URL,echo=False)

# Session factory to create test sessions
TestSessionLocal = sessionmaker(
    bind=engine,
    class_ = AsyncSession,
    expire_on_commit=False
)

#---------------------------------------------------------FIXTURES---------------------------------------------------------
#--------------------------------------------Functions that provide setup for tests----------------------------------------

# --- FIXTURE 1: Create/destroy tables once ---
@pytest.fixture(scope="session")
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    await seed_furniture(engine)
    await seed_quickpicks(engine)
    await seed_scenarios(engine)
    await seed_users(engine)
    yield # cleanup
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)

# --- FIXTURE 2: Give tests an HTTP client ---
@pytest.fixture(scope="session")
async def client(setup_database):
    # 1. Open a test database session
    async with TestSessionLocal() as session:
        # 2. Define a replacement for get_db()
        async def override_get_db():
            yield session
        # 3. Tell app to use the replacement
        app.dependency_overrides[get_db] = override_get_db
        # 4. Create an HTTP client wired to the app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac # what each test recieves
        # 5. Cleanup: remove the override
        app.dependency_overrides.clear()

#---------------------------------------------------------TESTS---------------------------------------------------------
#---------------------------------------Every Test Function Takes "client" as parameter---------------------------------
#------------------------------------ pytest automatically calls the fixture as passes it in----------------------------

state = {}

@pytest.mark.asyncio
async def test_register(client):
    print("--------------------------DEFAULT TESTS--------------------------")
    print("1. Registering User A")
    response = await client.post("/registerUser", json= {
        "email": "maksym@test.com",
        "password": "TestPass123"
    })
    assert response.status_code == 200
    response = response.json()
    state["token_A"] = response["access_token"]
    state["headers_A"] = {"Authorization": f"Bearer {state['token_A']}"}

    print("2. Registering User B")
    response = await client.post("/registerUser", json= {
        "email": "angelika@test.com",
        "password": "TestPass123"
    })
    assert response.status_code == 200
    response = response.json()
    state["token_B"] = response["access_token"]
    state["headers_B"] = {"Authorization": f"Bearer {state['token_B']}"}

    print("3. Update User A")
    response = await client.post("/updateUser",
        headers=state["headers_A"],
        json= {
            "name": "Maksym",
            "city": "San Diego",
            "state": "CA"
        })
    assert response.status_code == 200
    
    print("4. Update User B")
    response = await client.post("/updateUser",
        headers = state["headers_B"],
        json = {
            "name": "Angelika",
            "city": "Miami",
            "state": "FL"
        })
    assert response.status_code == 200

    print("5. GET User A")
    response = await client.get("/me", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    user_idA = response["id"]
    state["user_idA"] = user_idA

    print("6. GET User B")
    response = await client.get("/me", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    user_idB = response["id"]
    state["user_idB"] = user_idB

@pytest.mark.asyncio
async def test_duplicate_email(client):
    print("Negative Test: Trying to register with duplicate email should return 409")
    response = await client.post("/registerUser", json={
        "email": "maksym@test.com",
        "password": "TestPass123"
    })
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_get_me_notoken(client):
    print("Negative Test: Accesing /me with no token should return 403")
    response = await client.get("/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_apt(client):
    print("--------------------------APARTMENTS TESTS--------------------------")
    print("1. Create Apartment User A")
    response = await client.post("/apartments/",headers=state["headers_A"])
    assert response.status_code == 200
    state["apt_idA"] = response.json()["id"]


    print("2. Create Apartment User B")
    response = await client.post("/apartments/",headers=state["headers_B"])
    assert response.status_code == 200

    print("3. Get Presets")
    response = await client.get("/apartments/presets")
    assert response.status_code == 200
    response = response.json()
    bedroomA,bedroomB = response["bedroom"][0]["id"],response["bedroom"][1]["id"]
    livingroomA,livingroomB = response["living_room"][0]["id"],response["living_room"][1]["id"]
    kitchenA,kitchenB = response["kitchen"][0]["id"],response["kitchen"][1]["id"]
    bathroomA,bathroomB = response["bathroom"][0]["id"],response["bathroom"][1]["id"]

    print("4. Apply Presets User A")
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_A"],
        json= {
            "preset_id": bedroomA, # bedroom
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_A"],
        json= {
            "preset_id": livingroomA, # living room
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_A"],
        json= {
            "preset_id": kitchenA, # kitchen
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_A"],
        json= {
            "preset_id": bathroomA, # bathroom
        })
    assert response.status_code == 200

    print("5. Apply Presets User B")
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_B"],
        json= {
            "preset_id": bedroomB, # bedroom
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_B"],
        json= {
            "preset_id": livingroomB, # living room
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_B"],
        json= {
            "preset_id": kitchenB, # kitchen
        })
    assert response.status_code == 200
    response = await client.post("/apartments/apply-preset",
        headers=state["headers_B"],
        json= {
            "preset_id": bathroomB, # bathroom
        })
    assert response.status_code == 200

    print("6. GET Apartment User A")
    response = await client.get("/apartments/me", headers=state["headers_A"])
    assert response.status_code == 200

    print("7. GET Apartment User B")
    response = await client.get("/apartments/me", headers=state["headers_B"])
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_create_apt_neg(client):
    print("Negative Test: Trying to create apartment for user that already has an apartment should return already created apartment")
    response = await client.post("/apartments/", headers=state["headers_A"])
    assert response.json()["id"] == state["apt_idA"]


@pytest.mark.asyncio
async def test_getvibe(client):
    print("--------------------------VIBE TESTS--------------------------")
    print("1. GET Vibe User A")
    response = await client.get("/vibe/me", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("2. GET Vibe User B")
    response = await client.get("/vibe/me", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("3. Compare Vibe A->B")
    response = await client.get(f"/vibe/compare/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("4. Compare Vibe B->A")
    response = await client.get(f"/vibe/compare/{state['user_idA']}", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

@pytest.mark.asyncio
async def test_scenarios(client):
    print("--------------------------SCENARIO TESTS--------------------------")
    print("1. GET Scenarios User A")
    response = await client.get("/scenarios/daily", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    print(json.dumps(response, indent= 2))
    scenario_A = response["scenario"]["id"]

    print("2. GET Scenario User B")
    response = await client.get("/scenarios/daily", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    print(json.dumps(response, indent= 2))
    scenario_B = response["scenario"]["id"]

    print("3. POST Answer Scenario User A")
    response = await client.post("/scenarios/answer", 
        headers=state["headers_A"],
        json = {
            "scenario_id": scenario_A,
            "selected_option": "a"
        })
    assert response.status_code == 200

    print("4. POST Answer Scenario User B")
    response = await client.post("/scenarios/answer",
        headers=state["headers_B"],
        json = {
            "scenario_id": scenario_B,
            "selected_option": "b"
        })
    assert response.status_code == 200

    print("3. GET history User A")
    response = await client.get("/scenarios/history", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("3. GET history User B")
    response = await client.get("/scenarios/history", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("4. GET Compare Scenarios A->B")
    response = await client.get(f"/scenarios/compare/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))

    print("4. GET Compare Scenarios B->A")
    response = await client.get(f"/scenarios/compare/{state['user_idA']}", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent = 2))


@pytest.mark.asyncio
async def test_discovery(client):
    print("--------------------------DISCOVERY TESTS--------------------------")
    print("1. GET Neighborhood User A")
    response = await client.get("/discovery/neighborhood", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("2. GET Neighborhood User B")
    response = await client.get("/discovery/neighborhood", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("3. GET Nearby Neighborhoods User A")
    response = await client.get("/discovery/nearby", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("4. GET Nearby Neighborhoods User B")
    response = await client.get("/discovery/nearby", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("5. GET Summary User B from User A")
    response = await client.get(f"/discovery/user/{state['user_idB']}/summary", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("6. GET Summary User A from User B")
    response = await client.get(f"/discovery/user/{state['user_idA']}/summary", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))


@pytest.mark.asyncio
async def test_quickpicks(client):
    print("--------------------------QUICKPICKS TESTS--------------------------")
    print("1.1 POST Interest A->B")
    response = await client.post(f"/interest/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["mutual"] == False

    print("1.2 GET Interests for A should return B")
    response = await client.get("/interest/sent", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert state["user_idB"] in response["sent_to"]

    print("2.1 POST Interest B->A")
    response = await client.post(f"/interest/{state['user_idA']}", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert response["mutual"] == True

    print("2.2 GET Interests for B should return A")
    response = await client.get("/interest/sent", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert state["user_idA"] in response["sent_to"]

    print("3. GET Mutual Interests")
    response = await client.get("/interest/mutual", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["matches"][0]["session_id"] is not None

    print("4.1 GET Session A->B")
    response = await client.get(f"/quickpicks/session/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["status"] == "pending_both" # Neither user has answered a question yet, so both should be pending
    state["session_id"] = response["session_id"]

    print("4.2 GET Session B->A")
    response = await client.get(f"/quickpicks/session/{state['user_idA']}", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert response["session_id"] == state["session_id"] # Making sure that session ids match between user A and B
    assert response["status"] == "pending_both"          # Neither user has answered a question yet, so both should be pending

    print("5.1 POST Answers User A")
    response = await client.post("/quickpicks/answer",
        headers=state["headers_A"],
        json={
            "session_id": state["session_id"],
            "question_index": 0,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_A"],
        json={
            "session_id": state["session_id"],
            "question_index": 1,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_A"],
        json={
            "session_id": state["session_id"],
            "question_index": 2,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_A"],
        json={
            "session_id": state["session_id"],
            "question_index": 3,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_A"],
        json={
            "session_id": state["session_id"],
            "question_index": 4,
            "selected_option": "a"
        })
    assert response.status_code == 200

    print("5.2 POST Answers User B")
    response = await client.post("/quickpicks/answer",
        headers=state["headers_B"],
        json={
            "session_id": state["session_id"],
            "question_index": 0,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_B"],
        json={
            "session_id": state["session_id"],
            "question_index": 1,
            "selected_option": "b"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_B"],
        json={
            "session_id": state["session_id"],
            "question_index": 2,
            "selected_option": "a"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_B"],
        json={
            "session_id": state["session_id"],
            "question_index": 3,
            "selected_option": "b"
        })
    assert response.status_code == 200
    response = await client.post("/quickpicks/answer",
        headers=state["headers_B"],
        json={
            "session_id": state["session_id"],
            "question_index": 4,
            "selected_option": "a"
        })
    assert response.status_code == 200
    
    print("6.1 GET Results User A")
    response = await client.get(f"/quickpicks/results/{state['session_id']}", headers=state["headers_A"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

    print("6.2 GET Results User B")
    response = await client.get(f"/quickpicks/results/{state['session_id']}", headers=state["headers_B"])
    assert response.status_code == 200
    print(json.dumps(response.json(), indent= 2))

@pytest.mark.asyncio
async def test_households(client):
    print("--------------------------HOUSEHOLDS TESTS--------------------------")
    print("1. POST Create Household User A")
    response = await client.post("/households/", headers=state["headers_A"], json={
        "name": "Casa"
    })
    assert response.status_code == 200
    response = response.json()
    state["household_id"] = response["id"]
    
    print("2. GET Household User A")
    response = await client.get("/households/me", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["household"]["id"] == state["household_id"]
    assert response["household"]["name"] == "Casa"

    print("3. POST Invite User A->B")
    response = await client.post(f"/households/invite/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200

    print("4.1 GET Household Invites User A")
    response = await client.get("/households/invites", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["received"] == []
    assert response["sent"][0]["id"] is not None
    state["invite_id"] = response["sent"][0]["id"]

    print("4.2 GET Household Invites User B")
    response = await client.get("/households/invites", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert response["received"][0]["id"] is not None
    assert response["sent"] == []

    print("5. POST Accept Invite User B")
    response = await client.post(f"/households/invites/{state['invite_id']}/accept", headers=state["headers_B"])
    assert response.status_code == 200

    print("6. GET Household User B")    # to verify user B now belongs to user A's household
    response = await client.get("/households/me", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert response["household"]["id"] == state["household_id"]
    assert response["household"]["name"] == "Casa"

    print("7. POST Propose Rule User A")
    response = await client.post(f"/households/{state['household_id']}/rules", headers=state["headers_A"],json={
        "text": "Angelika doesn't step on bathroom mats with shoes on."
    })
    assert response.status_code == 200
    response = response.json()
    state["rule_id"] = response["id"]
    assert response["text"] == "Angelika doesn't step on bathroom mats with shoes on."

    print("8. GET Rules User A")
    response = await client.get(f"/households/{state['household_id']}/rules", headers=state["headers_A"])
    assert response.status_code == 200
    response = response.json()
    assert response["rules"][0]["yes_votes"] == 1   # making sure User A's vote is automatically added
    assert response["rules"][0]["my_vote"] == True

    print("9. POST Vote On Rule User B")
    response = await client.post(f"/households/rules/{state['rule_id']}/vote", headers=state["headers_B"], json={
        "vote": True
    })
    assert response.status_code == 200
    
    print("10. GET Rules User B")
    response = await client.get(f"/households/{state['household_id']}/rules", headers=state["headers_B"])
    assert response.status_code == 200
    response = response.json()
    assert response["rules"][0]["yes_votes"] == 2
    assert response["rules"][0]["my_vote"] == True
    assert response["rules"][0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_create_household_neg(client):
    print("Negative Test: Trying to create a household while already in a household should return 409")
    response = await client.post("/households/", headers=state["headers_A"], json={
        "name": "Casa"
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_messaging(client):
    print("--------------------------MESSAGING TESTS--------------------------")
    from sqlalchemy import insert as sa_insert
    from app.models import messages as messages_table
    from datetime import datetime, timezone, timedelta

    # ── DM Creation ──
    print("1. POST Create DM A->B")
    response = await client.post(f"/conversations/dm/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == True
    state["dm_conv_id"] = data["conversation_id"]

    print("2. POST Create DM A->B again (idempotent — same conv returned)")
    response = await client.post(f"/conversations/dm/{state['user_idB']}", headers=state["headers_A"])
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == False
    assert data["conversation_id"] == state["dm_conv_id"]

    print("3. POST Create DM B->A (same pair — same conv returned)")
    response = await client.post(f"/conversations/dm/{state['user_idA']}", headers=state["headers_B"])
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == False
    assert data["conversation_id"] == state["dm_conv_id"]

    # ── DM Negative Cases ──
    print("4. Negative: Self-DM should return 400")
    response = await client.post(f"/conversations/dm/{state['user_idA']}", headers=state["headers_A"])
    assert response.status_code == 400

    print("5. Register User C (no Quick Picks with A)")
    response = await client.post("/registerUser", json={
        "email": "charlie@test.com",
        "password": "TestPass123"
    })
    assert response.status_code == 200
    state["token_C"] = response.json()["access_token"]
    state["headers_C"] = {"Authorization": f"Bearer {state['token_C']}"}
    response = await client.post("/updateUser", headers=state["headers_C"], json={
        "name": "Charlie", "city": "Austin", "state": "TX"
    })
    assert response.status_code == 200
    response = await client.get("/me", headers=state["headers_C"])
    state["user_idC"] = response.json()["id"]

    print("6. Negative: DM without completed Quick Picks should return 400")
    response = await client.post(f"/conversations/dm/{state['user_idC']}", headers=state["headers_A"])
    assert response.status_code == 400

    print("7. Negative: DM to nonexistent user should return 404")
    response = await client.post("/conversations/dm/99999", headers=state["headers_A"])
    assert response.status_code == 404

    # ── List Conversations ──
    print("8. GET Conversations User A (should have DM + group from household)")
    response = await client.get("/conversations", headers=state["headers_A"])
    assert response.status_code == 200
    convos = response.json()["conversations"]
    conv_types = [c["type"] for c in convos]
    assert "dm" in conv_types
    assert "group" in conv_types
    state["group_conv_id"] = next(c["id"] for c in convos if c["type"] == "group")

    print("9. GET Conversations User B (should also have DM + group)")
    response = await client.get("/conversations", headers=state["headers_B"])
    assert response.status_code == 200
    assert len(response.json()["conversations"]) == 2

    print("10. GET Conversations User C (should be empty)")
    response = await client.get("/conversations", headers=state["headers_C"])
    assert response.status_code == 200
    assert response.json()["conversations"] == []

    # ── Empty Messages ──
    print("11. GET Messages from DM (should be empty)")
    response = await client.get(f"/conversations/{state['dm_conv_id']}/messages", headers=state["headers_A"])
    assert response.status_code == 200
    assert response.json()["messages"] == []

    print("12. Negative: Non-participant can't read messages")
    response = await client.get(f"/conversations/{state['dm_conv_id']}/messages", headers=state["headers_C"])
    assert response.status_code == 403

    # ── Mark as Read ──
    print("13. POST Mark DM as read User A")
    response = await client.post(f"/conversations/{state['dm_conv_id']}/read", headers=state["headers_A"])
    assert response.status_code == 200

    print("14. Negative: Non-participant can't mark as read")
    response = await client.post(f"/conversations/{state['dm_conv_id']}/read", headers=state["headers_C"])
    assert response.status_code == 403

    # ── Insert Messages Directly & Test Retrieval ──
    print("15. Insert 5 messages into DM via TestSessionLocal")
    # Offset message timestamps 10s in the past so mark_read (which uses now())
    # is always after all messages — avoids millisecond race in back-to-back test calls
    base_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
    msg_ids = []
    async with TestSessionLocal() as db:
        for i in range(5):
            sender = state["user_idA"] if i % 2 == 0 else state["user_idB"]
            result = await db.execute(
                sa_insert(messages_table).values(
                    conversation_id=state["dm_conv_id"],
                    sender_id=sender,
                    body=f"Test message {i+1}",
                    created_at=base_time + timedelta(seconds=i),
                ).returning(messages_table.c.id)
            )
            msg_ids.append(result.scalar_one())
        await db.commit()

    print("16. GET Messages — should return all 5 in ASC order")
    response = await client.get(f"/conversations/{state['dm_conv_id']}/messages", headers=state["headers_A"])
    assert response.status_code == 200
    msgs = response.json()["messages"]
    assert len(msgs) == 5
    assert msgs[0]["body"] == "Test message 1"
    assert msgs[4]["body"] == "Test message 5"
    assert msgs[0]["sender_name"] == "Maksym"
    assert msgs[1]["sender_name"] == "Angelika"

    print("17. GET Messages with cursor pagination (?before=msg3 should return msg1, msg2)")
    response = await client.get(
        f"/conversations/{state['dm_conv_id']}/messages?before={msg_ids[2]}",
        headers=state["headers_A"]
    )
    assert response.status_code == 200
    msgs = response.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["body"] == "Test message 1"
    assert msgs[1]["body"] == "Test message 2"

    print("18. GET Messages with limit=2 (should return last 2 in ASC)")
    response = await client.get(
        f"/conversations/{state['dm_conv_id']}/messages?limit=2",
        headers=state["headers_A"]
    )
    assert response.status_code == 200
    msgs = response.json()["messages"]
    assert len(msgs) == 2
    assert msgs[0]["body"] == "Test message 4"
    assert msgs[1]["body"] == "Test message 5"

    # ── Unread Counts ──
    print("19. GET Conversations User B — should have unread messages from A")
    response = await client.get("/conversations", headers=state["headers_B"])
    assert response.status_code == 200
    dm = next(c for c in response.json()["conversations"] if c["type"] == "dm")
    assert dm["unread_count"] > 0  # B hasn't read any messages

    print("20. POST Mark as read User B, then verify unread = 0")
    response = await client.post(f"/conversations/{state['dm_conv_id']}/read", headers=state["headers_B"])
    assert response.status_code == 200
    response = await client.get("/conversations", headers=state["headers_B"])
    dm = next(c for c in response.json()["conversations"] if c["type"] == "dm")
    assert dm["unread_count"] == 0

    # ── Group Chat (from household) ──
    print("21. GET Group chat messages (accessible by A)")
    response = await client.get(f"/conversations/{state['group_conv_id']}/messages", headers=state["headers_A"])
    assert response.status_code == 200

    print("22. GET Group chat messages (accessible by B)")
    response = await client.get(f"/conversations/{state['group_conv_id']}/messages", headers=state["headers_B"])
    assert response.status_code == 200

    print("23. Negative: User C can't access group chat")
    response = await client.get(f"/conversations/{state['group_conv_id']}/messages", headers=state["headers_C"])
    assert response.status_code == 403

    # ── Conversation Participants ──
    print("24. DM participants should be A and B")
    response = await client.get("/conversations", headers=state["headers_A"])
    dm = next(c for c in response.json()["conversations"] if c["type"] == "dm")
    participant_ids = sorted([p["id"] for p in dm["participants"]])
    assert participant_ids == sorted([state["user_idA"], state["user_idB"]])

    print("25. Last message in conversation list should be 'Test message 5'")
    assert dm["last_message"]["body"] == "Test message 5"
