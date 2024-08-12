from typing import Any, Union
from . import base
import subprocess
from uuid import UUID
from include.llm.base import AbstractLLMClient
from include.utils import prompt_with_file, BASE_PROMPT_PATH
import uuid
from collections import OrderedDict
import shlex

DEFAULT="default"

# prompts
EXECUTE_FPATH="execute/"
GENERATE_API_CALL="generate_api_call.txt"
CLEAN_RESPONSE="clean_response.txt"

class AWSApiCall:
    def __init__(self, cli_changelog: OrderedDict[UUID, str], outputs: OrderedDict[UUID, str]) -> None:
        self.cli_changelog=cli_changelog
        self.outputs=outputs

    def generate_new_uuid(self) -> UUID:
        """
        Generate a new UUID that doesn't exist in self.cli_changelog's keys.
        """
        while True:
            new_uuid = uuid.uuid4()
            if new_uuid not in self.cli_changelog:
                return new_uuid

class AWSExecutor():
    """
    An execution engine to run aws commands from user's request.
    """
    def __init__(self, profile_name: str, llm: AbstractLLMClient) -> None:
        self.profile_name=profile_name
        self.api_call = AWSApiCall({}, {})
        self.llm = llm

    def generate_api_call(self, prompt: str) -> UUID:
        """
        Generates api call with claude and appends the specific 
        profile being used.
        
        Can optionally be given error_msgs and the previous_api_call as additional 
        context for generating the api call.
        """
        # 1. generate new uuid for this api call
        new_call_uuid = self.api_call.generate_new_uuid()

        # 2. generate the api cli command with claude.
        api_call_prompt: str
        if len(self.api_call.cli_changelog) == 0:
            with open(BASE_PROMPT_PATH + EXECUTE_FPATH + GENERATE_API_CALL, "r", encoding="utf8") as fp:
                sys_prompt = fp.read()
                api_call_prompt = sys_prompt.format(prompt)
        else:
            # If nonzero changelog, need previous execution data integrated.
            pass

        cli_command = self.llm.query(api_call_prompt, "", False, temperature=0.3)

        # 3. append the profile name arg to the command
        cli_command += f" --profile {self.profile_name}"

        # 4. set the changelog to the new command
        self.api_call.cli_changelog[new_call_uuid] = cli_command

        return new_call_uuid

    def execute_api_call(self, call_uuid: UUID) -> str:
        """
        Executes an api call and gets the output
        """

        # 1. get api call 
        api_call = self.api_call.cli_changelog[call_uuid]

        # 2. trigger call
        api_call_splitted = shlex.split(api_call)
        output = subprocess.check_output(api_call_splitted)

        # 3. get output
        return output

    def execute(self, prompt: str) -> str:
        """
        Call the execution engine to generate output back to user.
        """

        # 1. Given the prompt, generate the api call nessecary, perfectly formatted with claude.
        api_call_uuid = self.generate_api_call(prompt)

        # 2. Execute the api call, and get response
        output = self.execute_api_call(api_call_uuid)
        self.api_call.outputs[api_call_uuid] = output

        # 3. spit response back out
        return output

class ExecutionAction(base.AbstractAction):

    """
    An execution engine using Gorilla LLM. This class should be provided with 
    a query regarding some AWS infra. Could be any of CRUD options. Regardless,
    should be capable of taking the query, converting it into an api call, and 
    returning the response as a json to the user.
    """

    def __init__(self, profile_name: str) -> None:
        super().__init__()
        self.aws_executor = AWSExecutor(profile_name, self.claude_client)

    def clean_ex_response(self, response: str, original_query: str) -> str:
        """
        Provided with the response form a goex fn, responds with a 
        user friendly, cleaned up response.
        """
        with open(BASE_PROMPT_PATH + EXECUTE_FPATH + CLEAN_RESPONSE, "r", encoding="utf8") as fp:
            sys_prompt = fp.read()
            cleaned_response_prompt = sys_prompt.format(original_query, response)

            return self.claude_client.query(cleaned_response_prompt, "", False, temperature=0.4)

    def trigger_action(self, input: str) -> Any:
        """
        Entry point to trigger an execution. The input should be the query representing 
        the api call to make
        """

        # 1. call goex engine
        response = self.aws_executor.execute(input)

        # 2. cleanup response for user.
        cleaned_response = self.clean_ex_response(response, input)        

        # 3. ret response to user.
        return cleaned_response

    def clean_input(self, input: str) -> str:
        """
        Overriding parent fn to take an input from the user,
        then generate a new prompt that specifically is focused
        towards READING some data from aws.
        
        This function should be only used as a context provider to then 
        pass into trigger_action. Not something the user will see.
        """

        return ""

    def requires_existing_resource_data(self, user_query: str) -> bool:
        """
        Given a user's query, this fn decides whether it's nessecary 
        to read some resources or not.
        """
        return False