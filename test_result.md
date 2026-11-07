#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
user_problem_statement: "VaultBridge Escrow — admin can delete an account completely. Deleting a sender/recipient account erases their login and EVERY deal they are on (for both parties) with all invoices, documents, messages, wallet scans and activity; Activity keeps one note 'A <role> account was deleted' with no name or email. Blocked while ETH is held in escrow on one of their deals. Admin accounts and own account protected."

backend:
  - task: "Account list + deletion preview + complete account deletion"
    implemented: true
    working: "NA"
    file: "backend/server.py (section '# ---------- accounts: admin view & complete deletion ----------')"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "GET /api/accounts, GET /api/accounts/{id}/deletion-preview, DELETE /api/accounts/{id}. Sample sender/recipient + sample deal only seeded on first start (settings key 'seeded'). new_transaction no longer needs existing party users. auto_scan skips writing if the deal was deleted mid-scan. Main agent smoke test passed."

frontend:
  - task: "Accounts page (admin) + delete dialog + Activity 'All activity' + no-deals empty state"
    implemented: true
    working: "NA"
    file: "frontend/src/pages/Accounts.jsx, pages/Activity.jsx, components/AppLayout.jsx, context/TxContext.jsx, components/ConfirmDialog.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "New /accounts page with Delete per sender/recipient, preview of what is erased, checkbox confirm, blocked state when ETH in escrow. Activity has This deal / All activity toggle for admin. When a user's last deal disappears, shows 'No deals yet' instead of endless Loading."

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 8
  run_ui: true

test_plan:
  current_focus:
    - "Account list + deletion preview + complete account deletion"
    - "Accounts page (admin) + delete dialog + Activity 'All activity' + no-deals empty state"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: "ETHERSCAN_API_KEY and OWNER_PASSWORD are NOT configured (user skipped). Creating deals via API fails with 503 (needs live ETH price) — expected. Seed synthetic test data directly in MongoDB for deletion tests. Do not delete the sample accounts sender@vaultbridge.demo / recipient@vaultbridge.demo or deal VB-ETH-2026-001."
