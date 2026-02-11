import requests
import sys

BASE_URL = "http://localhost:8000/api"

def test_projects():
    print("Testing Projects API...")
    
    # 1. List Projects (Should have default)
    try:
        res = requests.get(f"{BASE_URL}/projects")
        if res.status_code != 200:
            print(f"FAILED: GET /projects returned {res.status_code}")
            return False
        projects = res.json()
        print(f"SUCCESS: Found {len(projects)} projects.")
        for p in projects:
            print(f"  - {p['name']} ({p['id']})")
    except Exception as e:
        print(f"FAILED: Could not connect to backend: {e}")
        return False

    # 2. Get Active Project
    try:
        res = requests.get(f"{BASE_URL}/projects/active")
        if res.status_code != 200:
            print(f"FAILED: GET /projects/active returned {res.status_code}")
            return False
        active = res.json()
        print(f"SUCCESS: Active project is {active['name']}")
    except Exception as e:
        print(f"FAILED: Error getting active project: {e}")
        return False

    # 3. Add New Project
    new_project = {
        "id": "test-project-1",
        "name": "Test Project 1",
        "path": "/tmp/test-project-1",
        "description": "A test project",
        "repoUrl": "",
        "agentPlatforms": ["Claude Code"],
        "planDocsPath": "plans"
    }
    
    try:
        res = requests.post(f"{BASE_URL}/projects", json=new_project)
        if res.status_code != 200:
            print(f"FAILED: POST /projects returned {res.status_code}: {res.text}")
            return False
        print("SUCCESS: Added new project")
    except Exception as e:
        print(f"FAILED: Error adding project: {e}")
        return False

    # 4. Switch Project
    try:
        res = requests.post(f"{BASE_URL}/projects/active/test-project-1")
        if res.status_code != 200:
            print(f"FAILED: POST /projects/active returned {res.status_code}: {res.text}")
            return False
        print("SUCCESS: Switched to new project")
        
        # Verify active
        res = requests.get(f"{BASE_URL}/projects/active")
        active = res.json()
        if active['id'] != 'test-project-1':
            print(f"FAILED: Active project is {active['id']}, expected test-project-1")
            return False
        print("SUCCESS: Verified active project switch")
        
    except Exception as e:
        print(f"FAILED: Error switching project: {e}")
        return False

    # 5. Switch back to default
    try:
        res = requests.post(f"{BASE_URL}/projects/active/default-skillmeat")
        if res.status_code != 200:
            print("FAILED: Could not switch back to default")
            return False
        print("SUCCESS: Switched back to default project")
    except Exception:
        pass

    return True

if __name__ == "__main__":
    if test_projects():
        print("\nAll backend tests passed!")
        sys.exit(0)
    else:
        print("\nBackend tests failed.")
        sys.exit(1)
