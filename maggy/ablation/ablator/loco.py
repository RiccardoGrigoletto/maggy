#
#   Copyright 2020 Logical Clocks AB
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

import json

from maggy.ablation.ablator import AbstractAblator
from maggy.core.environment.singleton import EnvSing
from maggy.core.exceptions import BadArgumentsError
from maggy.core.exceptions import NotSupportedError
from maggy.trial import Trial


class LOCO(AbstractAblator):
    def __init__(self, ablation_study, final_store):
        super().__init__(ablation_study, final_store)
        self.base_dataset_generator = self.get_dataset_generator(ablated_feature=None)

    def get_number_of_trials(self):
        # the final ' + 1 ' is for the base (reference) trial with all the components
        return (
            len(self.ablation_study.features.included_features)
            + len(self.ablation_study.model.layers.included_layers)
            + len(self.ablation_study.model.layers.included_groups)
            + len(self.ablation_study.model.custom_model_generators)
            + 1
        )

    def get_dataset_generator(
        self, ablated_feature=None, dataset_type="tfrecord", shuffle_buffer_size=10000
    ):

        # for dataset generators provided by users
        if self.ablation_study.custom_dataset_generator:
            return self.ablation_study.custom_dataset_generator
        else:
            training_dataset_name = self.ablation_study.hops_training_dataset_name
            training_dataset_version = self.ablation_study.hops_training_dataset_version
            label_name = self.ablation_study.label_name

            if dataset_type == "tfrecord":

                def create_tf_dataset(num_epochs, batch_size):
                    conn = EnvSing.get_instance().connect_hsfs(engine="training")
                    fs = conn.get_feature_store()

                    td = fs.get_training_dataset(
                        training_dataset_name, training_dataset_version
                    )

                    feature_names = [f.name for f in td.schema]

                    if ablated_feature is not None:
                        feature_names.remove(ablated_feature)

                    return td.tf_data(
                        target_name=label_name, feature_names=feature_names
                    ).tf_record_dataset(
                        batch_size=batch_size, num_epochs=num_epochs, process=True
                    )

                return create_tf_dataset
            else:
                raise NotSupportedError(
                    "dataset type",
                    dataset_type,
                    "Use 'tfrecord' or write your own custom dataset generator.",
                )

    def get_model_generator(self, layer_identifier=None, custom_model_generator=None):

        if layer_identifier is not None and custom_model_generator is not None:
            raise BadArgumentsError(
                "get_model_generator",
                "At least one of 'layer_identifier' or 'custom_model_generator' should be 'None'.",
            )

        # if this trial relates to a custom model, then return the provided custom model generator
        if custom_model_generator:
            return custom_model_generator[0]
        # if this is a model ablation of a base model, construct a new model generator
        # using the layer_identifier
        base_model_generator = self.ablation_study.model.base_model_generator
        if layer_identifier is None:
            return base_model_generator

        def model_generator():
            import tensorflow as tf

            base_model = base_model_generator()

            list_of_layers = [
                base_layer for base_layer in base_model.get_config()["layers"]
            ]
            if type(layer_identifier) is str:
                # ablation of a single layer
                for base_layer in reversed(list_of_layers[1:-1]):
                    # the first (input) and last (output) layers should not be considered, hence list_of_layers[1:-1]
                    if base_layer["config"]["name"] == layer_identifier:
                        list_of_layers.remove(base_layer)
                        break
            elif type(layer_identifier) is set:
                # ablation of a layer group - all the layers in the group should be removed together
                if len(layer_identifier) > 1:
                    # group of layers (non-prefix)
                    for base_layer in reversed(list_of_layers[1:-1]):
                        if base_layer["config"]["name"] in layer_identifier:
                            list_of_layers.remove(base_layer)
                elif len(layer_identifier) == 1:
                    # layer_identifier is a prefix
                    prefix = list(layer_identifier)[0].lower()
                    for base_layer in reversed(list_of_layers[1:-1]):
                        if base_layer["config"]["name"].lower().startswith(prefix):
                            list_of_layers.remove(base_layer)

            base_json = base_model.to_json()
            new_dict = json.loads(base_json)
            new_dict["config"]["layers"] = list_of_layers
            new_json = json.dumps(new_dict)
            new_model = tf.keras.models.model_from_json(new_json)

            return new_model

        return model_generator

    def initialize(self):
        """
        Prepares all the trials for LOCO policy (Leave One Component Out).
        In total `n+1` trials will be generated where `n` is equal to the number of components
        (e.g. features and layers) that are included in the ablation study
        (i.e. the components that will be removed one-at-a-time). The first trial will include all the components and
        can be regarded as the base for comparison.
        """

        # 0 - add first trial with all the components (base/reference trial)
        self.trial_buffer.append(
            Trial(self.create_trial_dict(None, None), trial_type="ablation")
        )

        # generate remaining trials based on the ablation study configuration:
        # 1 - generate feature ablation trials
        for feature in self.ablation_study.features.included_features:
            self.trial_buffer.append(
                Trial(
                    self.create_trial_dict(ablated_feature=feature),
                    trial_type="ablation",
                )
            )

        # 2 - generate single-layer ablation trials
        for layer in self.ablation_study.model.layers.included_layers:
            self.trial_buffer.append(
                Trial(
                    self.create_trial_dict(layer_identifier=layer),
                    trial_type="ablation",
                )
            )

        # 3 - generate layer-groups ablation trials
        # each element of `included_groups` is a frozenset of a set, so we cast again to get a set
        # why frozensets in the first place? because a set can only contain immutable elements
        # hence elements (layer group identifiers) are frozensets

        for layer_group in self.ablation_study.model.layers.included_groups:
            self.trial_buffer.append(
                Trial(
                    self.create_trial_dict(layer_identifier=set(layer_group)),
                    trial_type="ablation",
                )
            )

        # 4 - generate ablation trials based on custom model generators

        for custom_model_generator in self.ablation_study.model.custom_model_generators:
            self.trial_buffer.append(
                Trial(
                    self.create_trial_dict(
                        custom_model_generator=custom_model_generator
                    ),
                    trial_type="ablation",
                )
            )

    def get_trial(self, trial=None):
        if self.trial_buffer:
            return self.trial_buffer.pop()
        else:
            return None

    def finalize_experiment(self, trials):
        return

    def create_trial_dict(
        self, ablated_feature=None, layer_identifier=None, custom_model_generator=None
    ):
        """
        Creates a trial dictionary that can be used for creating a Trial instance.

        :param ablated_feature: a string representing the name of a feature, or None
        :param layer_identifier: A string representing the name of a single layer, or a set representing a layer group.
        If the set has only one element, it is regarded as a prefix, so all layers with that prefix in their names
        would be regarded as a layer group. Otherwise, if the set has more than one element, the layers with
        names corresponding to those elements would be regarded as a layer group.
        :return: A trial dictionary that can be passed to maggy.Trial() constructor.
        :rtype: dict
        """

        trial_dict = {}

        # 1 - determine the dataset generation logic
        if ablated_feature is None:
            trial_dict["dataset_function"] = self.base_dataset_generator
            trial_dict["ablated_feature"] = "None"
        else:
            trial_dict["dataset_function"] = self.get_dataset_generator(
                ablated_feature, dataset_type="tfrecord"
            )
            trial_dict["ablated_feature"] = ablated_feature

        # 2 - determine the model generation logic
        # 2.1 - no model ablation

        if layer_identifier is None and custom_model_generator is None:
            trial_dict[
                "model_function"
            ] = self.ablation_study.model.base_model_generator
            trial_dict["ablated_layer"] = "None"
        # 2.2 - layer ablation based on base model generator
        elif layer_identifier is not None and custom_model_generator is None:
            trial_dict["model_function"] = self.get_model_generator(
                layer_identifier=layer_identifier
            )
            if type(layer_identifier) is str:
                trial_dict["ablated_layer"] = layer_identifier
            elif type(layer_identifier) is set:
                if len(layer_identifier) > 1:
                    trial_dict["ablated_layer"] = str(list(layer_identifier))
                elif len(layer_identifier) == 1:
                    trial_dict["ablated_layer"] = "Layers prefixed " + str(
                        list(layer_identifier)[0]
                    )
        # 2.3 - model ablation based on a custom model generator
        elif layer_identifier is None and custom_model_generator is not None:
            trial_dict["model_function"] = self.get_model_generator(
                custom_model_generator
            )
            trial_dict["ablated_layer"] = "Custom model: " + custom_model_generator[1]

        return trial_dict
