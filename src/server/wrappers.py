from src.actions.construct import ConstructTFConfigAction
from src.actions.edit import EditTFConfigAction
from src.actions.deploy import DeployCFStackAction
from src.db.supa import SupaClient, ChatSessionState, TFConfigDNEException
from src.model.stack import TerraformConfig

from include.utils import BASE_PROMPT_PATH, prompt_with_file
from include.llm.gpt import GPTClient

CONSTRUCT_OR_OTHER_PROMPT = "construct_or_other.txt"
IRRELEVANT_QUERY_HANDLER = "handle_irrelevant_query.txt"

def construction_wrapper(user_query: str, chat_session_id: int, client: SupaClient) -> str:
    """
    Constructs a terraform config based off user query. Persists config in supabase and updates
    chat session state. Returns qualitative response for user.

    todo Caches ChatSession config in mem and disk for further use.
    Caches user supa client connection in mem.
    """
    action = ConstructTFConfigAction()

    try:
        action_response = action.trigger_action(user_query)
        stack = action.tf_config

        client.edit_entire_tf_config(chat_session_id, stack)

        # TODO add cloudformation stack linter to see if
        # the stack is deployable, and update the state as such
        client.update_chat_session_state(chat_session_id, ChatSessionState.QUERIED)

        return action_response
    except Exception as e:
        print(
            f"Failed to construct tf config for user. \nUser request: {user_query} \n\nError: {e}"
        )
        client.update_chat_session_state(
            chat_session_id, ChatSessionState.QUERIED_NOT_DEPLOYABLE
        )


def edit_wrapper(user_query: str, chat_session_id: str, client: SupaClient, config: TerraformConfig) -> str | None:
    """
    Using the user query, and the cf stack retrieved from supabase with the chat
    session id, edits the cf stack and responds qualitativly to the user.

    also, updates state and persists chat stack.
    """

    try:
        # 2. construct edit action
        action = EditTFConfigAction(config)

        # 3. trigger action
        action_result = action.trigger_action(user_query)
        new_config = action.new_config
        print(new_config)

        # 4. persist new stack in supa
        client.edit_entire_tf_config(chat_session_id, new_config)
        client.update_chat_session_state(chat_session_id, ChatSessionState.QUERIED)

        return action_result
    except TFConfigDNEException:
        print("Stack dne yet. Edit wrapper incorrect.")
        return None
    except Exception as e:
        print(
            f"Failed to edit cf stack for user. \nUser request: {user_query} \n\nError: {e}"
        )
        client.update_chat_session_state(
            chat_session_id, ChatSessionState.QUERIED_NOT_DEPLOYABLE
        )
        return None

def deploy_wrapper(user_id: int, chat_session_id: int) -> str:
    """
    A wrapper around the deployment action. Allows us to deploy a 
    cf stack from the user.
    """
    supa_client = SupaClient(user_id)

    # 1. Get the following info
    # user_stack: CloudFormationStack,
    user_stack = supa_client.get_tf_config(chat_session_id)
    # chat_session_id: int,
    # state_manager: SupaClient,
    user_aws_secret_key, user_aws_access_key_id = supa_client.get_user_aws_creds()

    deployment_action = DeployCFStackAction(user_stack, chat_session_id, supa_client, user_aws_secret_key, user_aws_access_key_id)

    # 2. Attempt deployment, return trigger_action response
    return deployment_action.trigger_action()


def handle_irrelevant_query(query: str, client: GPTClient) -> str:
    """
    Hanldes and responds to a query that isn't clearly about creating or 
    deploying infra. If the query is asking some questions about aws, or how 
    this thing works, then answer, else respond with a msg saying pls be specific.
    """
    response = prompt_with_file(
        BASE_PROMPT_PATH + IRRELEVANT_QUERY_HANDLER,
        query,
        client,
    )

    return response

def query_wrapper(user_query: str, user_id: int, chat_session_id: int) -> str:
    """
    A wrapper around a Cirrus query. Determines whether the input query is a 
    construction call, or an edit call. For now, we're not allowing deployments from chat.
    """

    # 1. Get state.
    supa_client = SupaClient(user_id)
    client = GPTClient()
    stack: TerraformConfig | None = None

    state = supa_client.get_chat_session_state(chat_session_id)
    if state == ChatSessionState.NOT_QUERIED:
        # 2. if never been queried before, only then can this be a construction action
        response = prompt_with_file(
            BASE_PROMPT_PATH + CONSTRUCT_OR_OTHER_PROMPT, 
            user_query, 
            client
        )

        if response.lower() == "true":
            print("Need to construct")
            response = construction_wrapper(user_query, chat_session_id, supa_client)
        else:
            response = handle_irrelevant_query(user_query, client)
    else:
        # 3. if exists, can only be edit. assumes that edit action will 
        # handle even if no edits are possible.

        if not stack:
            stack = supa_client.get_tf_config(chat_session_id)

        if stack:
            response = edit_wrapper(user_query, chat_session_id, supa_client, stack)

            if response is None:
                response = handle_irrelevant_query(user_query, client)
        else:
            print("State was not NOT_QUERIED, but stack dne.")

    return response
