import os



class EnvironmentSingleton:
    __instance = None
    def __new__(cls, *args):
        if cls.__instance is None:
            # check hopsworks availability
            if "REST_ENDPOINT" in os.environ:
                from maggy.core.environment import HopsEnvironment
                cls.__instance = HopsEnvironment(cls, *args)

            #todo: add condition for databricks
            elif False:
                from maggy.core.environment import DatabricksEnvironment
                cls.__instance = DatabricksEnvironment(cls, *args)
            else:
                from maggy.core.environment import BaseEnvironment
                cls.__instance = BaseEnvironment(cls, *args)

            if cls.__instance is None:
                raise AttributeError("Environment is None.")

        return cls.__instance