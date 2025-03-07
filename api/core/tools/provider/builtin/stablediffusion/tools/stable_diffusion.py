from core.tools.tool.builtin_tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage, ToolParamter, ToolParamterOption
from core.tools.entities.common_entities import I18nObject
from core.tools.errors import ToolProviderCredentialValidationError

from typing import Any, Dict, List, Union
from httpx import post
from os.path import join
from base64 import b64decode, b64encode
from PIL import Image

import json
import io

from copy import deepcopy

DRAW_TEXT_OPTIONS = {
    "prompt": "",
    "negative_prompt": "",
    "seed": -1,
    "subseed": -1,
    "subseed_strength": 0,
    "seed_resize_from_h": -1,
    'sampler_index': 'DPM++ SDE Karras',
    "seed_resize_from_w": -1,
    "batch_size": 1,
    "n_iter": 1,
    "steps": 10,
    "cfg_scale": 7,
    "width": 1024,
    "height": 1024,
    "restore_faces": False,
    "do_not_save_samples": False,
    "do_not_save_grid": False,
    "eta": 0,
    "denoising_strength": 0,
    "s_min_uncond": 0,
    "s_churn": 0,
    "s_tmax": 0,
    "s_tmin": 0,
    "s_noise": 0,
    "override_settings": {},
    "override_settings_restore_afterwards": True,
    "refiner_switch_at": 0,
    "disable_extra_networks": False,
    "comments": {},
    "enable_hr": False,
    "firstphase_width": 0,
    "firstphase_height": 0,
    "hr_scale": 2,
    "hr_second_pass_steps": 0,
    "hr_resize_x": 0,
    "hr_resize_y": 0,
    "hr_prompt": "",
    "hr_negative_prompt": "",
    "script_args": [],
    "send_images": True,
    "save_images": False,
    "alwayson_scripts": {}
}

class StableDiffusionTool(BuiltinTool):
    def _invoke(self, user_id: str, tool_paramters: Dict[str, Any]) \
        -> Union[ToolInvokeMessage, List[ToolInvokeMessage]]:
        """
            invoke tools
        """
        # base url
        base_url = self.runtime.credentials.get('base_url', None)
        if not base_url:
            return self.create_text_message('Please input base_url')
        model = self.runtime.credentials.get('model', None)
        if not model:
            return self.create_text_message('Please input model')
        
        # set model
        try:
            url = join(base_url, 'sdapi/v1/options')
            response = post(url, data=json.dumps({
                'sd_model_checkpoint': model
            }))
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError('Failed to set model, please tell user to set model')
        except Exception as e:
            raise ToolProviderCredentialValidationError('Failed to set model, please tell user to set model')

        
        # prompt
        prompt = tool_paramters.get('prompt', '')
        if not prompt:
            return self.create_text_message('Please input prompt')
        
        # get negative prompt
        negative_prompt = tool_paramters.get('negative_prompt', '')
        
        # get size
        width = tool_paramters.get('width', 1024)
        height = tool_paramters.get('height', 1024)

        # get steps
        steps = tool_paramters.get('steps', 1)

        # get lora
        lora = tool_paramters.get('lora', '')

        # get image id
        image_id = tool_paramters.get('image_id', '')
        if image_id.strip():
            image_variable = self.get_default_image_variable()
            if image_variable:
                image_binary = self.get_variable_file(image_variable.name)
                if not image_binary:
                    return self.create_text_message('Image not found, please request user to generate image firstly.')
                
                # convert image to RGB
                image = Image.open(io.BytesIO(image_binary))
                image = image.convert("RGB")
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                image_binary = buffer.getvalue()
                image.close()

                return self.img2img(base_url=base_url,
                                    lora=lora,
                                    image_binary=image_binary,
                                    prompt=prompt,
                                    negative_prompt=negative_prompt,
                                    width=width,
                                    height=height,
                                    steps=steps)
            
        return self.text2img(base_url=base_url,
                             lora=lora,
                             prompt=prompt,
                             negative_prompt=negative_prompt,
                             width=width,
                             height=height,
                             steps=steps)
        
    def img2img(self, base_url: str, lora: str, image_binary: bytes, 
                prompt: str, negative_prompt: str,
                width: int, height: int, steps: int) \
        -> Union[ToolInvokeMessage, List[ToolInvokeMessage]]:
        """
            generate image
        """
        draw_options = {
            "init_images": [b64encode(image_binary).decode('utf-8')],
            "prompt": "",
            "negative_prompt": negative_prompt,
            "denoising_strength": 0.9,
            "width": width,
            "height": height,
            "cfg_scale": 7,
            "sampler_name": "Euler a",
            "restore_faces": False,
            "steps": steps,
            "script_args": ["outpainting mk2"]
        }

        if lora:
            draw_options['prompt'] = f'{lora},{prompt}'
        else:
            draw_options['prompt'] = prompt

        try:
            url = join(base_url, 'sdapi/v1/img2img')
            response = post(url, data=json.dumps(draw_options), timeout=120)
            if response.status_code != 200:
                return self.create_text_message('Failed to generate image')
            
            image = response.json()['images'][0]

            return self.create_blob_message(blob=b64decode(image), 
                                            meta={ 'mime_type': 'image/png' },
                                            save_as=self.VARIABLE_KEY.IMAGE.value)
            
        except Exception as e:
            return self.create_text_message('Failed to generate image')

    def text2img(self, base_url: str, lora: str, prompt: str, negative_prompt: str, width: int, height: int, steps: int) \
        -> Union[ToolInvokeMessage, List[ToolInvokeMessage]]:
        """
            generate image
        """
        # copy draw options
        draw_options = deepcopy(DRAW_TEXT_OPTIONS)

        if lora:
            draw_options['prompt'] = f'{lora},{prompt}'
        else:
            draw_options['prompt'] = prompt
            
        draw_options['width'] = width
        draw_options['height'] = height
        draw_options['steps'] = steps
        draw_options['negative_prompt'] = negative_prompt
        
        try:
            url = join(base_url, 'sdapi/v1/txt2img')
            response = post(url, data=json.dumps(draw_options), timeout=120)
            if response.status_code != 200:
                return self.create_text_message('Failed to generate image')
            
            image = response.json()['images'][0]

            return self.create_blob_message(blob=b64decode(image), 
                                            meta={ 'mime_type': 'image/png' },
                                            save_as=self.VARIABLE_KEY.IMAGE.value)
            
        except Exception as e:
            return self.create_text_message('Failed to generate image')


    def get_runtime_parameters(self) -> List[ToolParamter]:
        parameters = [
            ToolParamter(name='prompt', 
                         label=I18nObject(en_US='Prompt', zh_Hans='Prompt'),
                         human_description=I18nObject(
                             en_US='Image prompt, you can check the official documentation of Stable Diffusion',
                             zh_Hans='图像提示词，您可以查看 Stable Diffusion 的官方文档',
                         ),
                         type=ToolParamter.ToolParameterType.STRING,
                         form=ToolParamter.ToolParameterForm.LLM,
                         llm_description='Image prompt of Stable Diffusion, you should describe the image you want to generate as a list of words as possible as detailed, the prompt must be written in English.',
                         required=True),
        ]
        if len(self.list_default_image_variables()) != 0:
            parameters.append(
                ToolParamter(name='image_id', 
                             label=I18nObject(en_US='image_id', zh_Hans='image_id'),
                             human_description=I18nObject(
                                en_US='Image id of the image you want to generate based on, if you want to generate image based on the default image, you can leave this field empty.',
                                zh_Hans='您想要生成的图像的图像 ID，如果您想要基于默认图像生成图像，则可以将此字段留空。',
                             ),
                             type=ToolParamter.ToolParameterType.STRING,
                             form=ToolParamter.ToolParameterForm.LLM,
                             llm_description='Image id of the original image, you can leave this field empty if you want to generate a new image.',
                             required=True,
                             options=[ToolParamterOption(
                                 value=i.name,
                                 label=I18nObject(en_US=i.name, zh_Hans=i.name)
                             ) for i in self.list_default_image_variables()])
            )

        return parameters
