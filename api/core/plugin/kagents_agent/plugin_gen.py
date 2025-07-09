import ast
import enum
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import uuid

import astor
import pinyin
from ruamel.yaml import YAML

from config import PROJECT_PATH

yaml = YAML()

AGENT_ID = "agentId"
TEMPLATE_CODE_PATH = os.path.join(PROJECT_PATH, "core/plugin/kagents_agent/source_code")
AGENTS_MANIFEST_PATH = "manifest.yaml"
AGENTS_PROVIDER_SOURCE_PATH = "template/kagents.yaml"
AGENTS_TOOLS_SOURCE_PATH = "template/tools.yaml"
AGENTS_AGENT_SOURCE_PATH = "template/agent.py"

AGENTS_PROVIDER_DIST_PATH = "provider/provider.yaml"
AGENTS_DIST_SOURCE_PATH = "provider/kagents.yaml"
MANIFEST_DIST_SOURCE_PATH = "manifest.yaml"
AGENTS_TOOLS_DIST_PATH = "tools/agent{}.yaml"
AGENTS_AGENT_DIST_PATH = "tools/agent{}.py"
AGENTS_CLASS_NAME = "agent{}"

PROVIDER_TOOLS_SECTION = "tools"

AGENT_HISTORY_FILE_NAME = "agent_history.txt"

# todo 统一标准
TYPE_MAPPER = {"text": "string", "file": "string", "string": "string"}


def generate_random_plugin_id():
    chars = string.ascii_lowercase + string.digits + "_-"
    name = "".join(secrets.choice(chars) for _ in range(secrets.randbelow(11) + 5))
    return f"{name}"


# copied from dify
class PluginInstallationSource(enum.StrEnum):
    Github = "github"
    Marketplace = "marketplace"
    Package = "package"
    Remote = "remote"


class PluginGen:
    def __init__(self, agent_info):
        self.agent_info = agent_info
        self.cur_agent_file_dir = ""
        self.clean_dir = []

    def start_tasks(self):
        agent_info = self.agent_info

        self.patch_agent_history(agent_info)

        self.generate_difypkg_files()

        # details in "https://docs.dify.ai/plugin-dev-en/0211-getting-started-dify-tool"
        self.generate_manifest_files()
        self.generate_provider_yaml_files(agent_info)
        self.generate_tools_yaml_files(agent_info)
        self.generate_agent_code_files(agent_info)

        pkg_path = os.path.join(
            PROJECT_PATH, f"{self.cur_agent_file_dir.split("/")[-1]}.difypkg"
        )

        cli_path = os.path.join(
            PROJECT_PATH, "core/plugin/kagents_agent/dify-plugin-linux-amd64"
        )

        subprocess.run(["chmod", "+x", cli_path], check=True)
        subprocess.run(
            [
                cli_path,
                "plugin",
                "package",
                self.cur_agent_file_dir,
            ],
            check=True,
        )
        pkg_bytes = b""
        with open(pkg_path, "rb") as f:
            pkg_bytes = f.read()
        return pkg_bytes

    def patch_agent_history(self, agent_info):
        history = []
        with open(AGENT_HISTORY_FILE_NAME, "a+") as f:
            f.seek(0)
            for line in f:
                try:
                    history.append(json.loads(line.strip()))
                except:
                    continue
            for agent in agent_info:
                f.write(json.dumps(agent) + "\n")
                history.append(agent)
        agent_info.clear()
        agent_info.extend(history)

    def generate_difypkg_files(self):
        try:
            dst_dir = uuid.uuid4().hex
            dst_dir = os.path.join(PROJECT_PATH, "core/plugin/kagents_agent/" + dst_dir)
            self.clean_dir.append(dst_dir)
            self.cur_agent_file_dir = dst_dir

            shutil.copytree(TEMPLATE_CODE_PATH, dst_dir, dirs_exist_ok=True)
        except Exception as e:
            print(e)

    def generate_manifest_files(self):

        try:
            path = os.path.join(self.cur_agent_file_dir, AGENTS_MANIFEST_PATH)

            with open(path, encoding="utf-8") as f:
                cur_working_yaml = yaml.load(f)

            cur_working_yaml["name"] = "kagent-agent"

            with open(
                os.path.join(self.cur_agent_file_dir, MANIFEST_DIST_SOURCE_PATH),
                "w",
                encoding="utf-8",
            ) as f:
                yaml.dump(cur_working_yaml, f)

        except Exception as e:
            print(e)

    def generate_provider_yaml_files(self, agent_info):

        try:
            path = os.path.join(self.cur_agent_file_dir, AGENTS_PROVIDER_SOURCE_PATH)

            with open(path, encoding="utf-8") as f:
                cur_working_yaml = yaml.load(f)

            if (
                PROVIDER_TOOLS_SECTION not in cur_working_yaml
                or cur_working_yaml[PROVIDER_TOOLS_SECTION] is None
            ):
                cur_working_yaml[PROVIDER_TOOLS_SECTION] = []

            for index, _ in enumerate(agent_info):
                cur_working_yaml[PROVIDER_TOOLS_SECTION].append(
                    AGENTS_TOOLS_DIST_PATH.format(index)
                )

            with open(
                os.path.join(self.cur_agent_file_dir, AGENTS_DIST_SOURCE_PATH),
                "w",
                encoding="utf-8",
            ) as f:
                yaml.dump(cur_working_yaml, f)

        except Exception as e:
            print(e)

    def generate_tools_yaml_files(self, agent_infos):
        for index, agent_info in enumerate(agent_infos):
            agent_title = agent_info.get("agentTitle", "none agentTitle is founded")
            agent_description = agent_info.get(
                "agentDescription", "none agent description is founded"
            )
            agent_id = agent_info.get("agentId", "none agent description is founded")

            path = os.path.join(self.cur_agent_file_dir, AGENTS_TOOLS_SOURCE_PATH)
            dist_path = os.path.join(
                self.cur_agent_file_dir, AGENTS_TOOLS_DIST_PATH.format(index)
            )

            os.makedirs(os.path.dirname(dist_path), exist_ok=True)
            shutil.copy(path, dist_path)

            with open(dist_path, encoding="utf-8") as f:
                cur_working_yaml = yaml.load(f)

            cur_working_yaml["identity"]["zh_Hans"] = agent_title
            cur_working_yaml["identity"]["name"] = agent_id
            cur_working_yaml["identity"]["label"]["zh_Hans"] = agent_description
            cur_working_yaml["identity"]["label"]["en_US"] = pinyin.get(
                agent_description, format="strip", delimiter=" "
            )

            cur_working_yaml["description"]["human"]["zh_Hans"] = agent_description
            cur_working_yaml["description"]["llm"] = agent_description

            # init
            cur_working_yaml["parameters"] = []
            cur_working_yaml["out_parameters"] = []
            cur_working_yaml["extra"]["python"]["source"] = []

            parameters = agent_info.get("defaultInputModesList")
            out_parameters = agent_info.get("defaultOutputModesList")
            if parameters:
                for parameter in parameters:
                    param_name = parameter.get("name", "none name is founded")
                    param_desc = parameter.get(
                        "description", "none description is founded"
                    )
                    param_req = parameter.get("required", False)
                    param_type = TYPE_MAPPER[parameter.get("type")]

                    # todo: support "form": "form"
                    param = {
                        "name": (
                            pinyin.get(param_name, format="strip", delimiter="")
                            if bool(re.search(r"[\u4e00-\u9fff]", param_name))
                            else param_name
                        ),
                        "form": "llm",
                        "human_description": {
                            "zh_Hans": param_desc,
                            "en_US": pinyin.get(
                                param_desc, format="strip", delimiter=" "
                            ),
                        },
                        "label": {
                            "zh_Hans": param_desc,
                            "en_US": pinyin.get(
                                param_desc, format="strip", delimiter=" "
                            ),
                        },
                        "llm_description": param_desc,
                        "required": param_req,
                        "type": param_type,
                    }
                    cur_working_yaml["parameters"].append(param)
            else:
                cur_working_yaml["parameters"] = None
            if out_parameters:
                for oparameter in out_parameters:
                    param_name = oparameter.get("name", "none name is founded")
                    param_desc = oparameter.get(
                        "description", "none description is founded"
                    )
                    param_req = oparameter.get("required", False)
                    param_type = oparameter.get("type")
                    param = {
                        "name": param_name,
                        "required": param_req,
                        "description": param_desc,
                        "type": param_type,
                    }
                    cur_working_yaml["out_parameters"].append(param)
            cur_working_yaml["api_key"] = agent_info.get(
                "apiKey", "none agentTitle is founded"
            )
            cur_working_yaml["extra"]["python"]["source"] = (
                AGENTS_TOOLS_DIST_PATH.format(index)
            )

            with open(dist_path, "w", encoding="utf-8") as f:
                yaml.dump(cur_working_yaml, f)

    def generate_agent_code_files(self, agent_info):
        path = os.path.join(self.cur_agent_file_dir, AGENTS_AGENT_SOURCE_PATH)
        for i in range(len(agent_info)):
            dist_path = os.path.join(
                self.cur_agent_file_dir, AGENTS_AGENT_DIST_PATH.format(i)
            )
            shutil.copy(path, dist_path)

            with open(dist_path, encoding="utf-8") as f:
                tree = ast.parse(f.read())

            class_nodes = [node for node in tree.body if isinstance(node, ast.ClassDef)]

            old_class_name = class_nodes[0].name
            new_class_name = AGENTS_CLASS_NAME.format(i)
            class_nodes[0].name = new_class_name

            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id == old_class_name:
                    node.id = new_class_name
                elif isinstance(node, ast.Attribute) and node.attr == old_class_name:
                    node.attr = new_class_name

            code = astor.to_source(tree)

            # replace all single-quoted strings with double-quoted strings using JSON escape rules
            code = re.sub(
                r"'([^'\\]*(?:\\.[^'\\]*)*)'", lambda m: json.dumps(m.group(1)), code
            )

            with open(dist_path, "w", encoding="utf-8") as f:
                f.write(code)

    def __del__(self):
        for item in self.clean_dir:
            if os.path.exists(item):
                shutil.rmtree(item)
