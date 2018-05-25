from dict_keys.model_metadata_keys import *
from util.Logger import Logger, StdoutOnlyLogger
from util.misc_util import dump_json, load_json
from env_settting import *
from time import strftime, localtime
import tensorflow as tf
import os
import sys
import traceback


def deco_exception_handle(func):
    """decorator for catch exception and log"""

    def wrapper(*args, **kwargs):
        self = args[0]
        log_func = self.log
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            log_func("KeyboardInterrupt detected abort process")
        except Exception as e:
            log_error_trace(log_func, e)

    return wrapper


def log_error_trace(log_func, e, head=""):
    exc_type, exc_value, exc_traceback = sys.exc_info()

    msg = '%s\n %s %s : %s \n' % (
        head,
        "".join(traceback.format_tb(exc_traceback)),
        e.__class__.__name__,
        e,
    )
    log_func(msg)


def deco_logging_func_name(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        log_func = self.log
        log_func(func.__name__)
        return func(*args, **kwargs)

    return wrapper


class ModelBuildFailError(BaseException):
    pass


class MetaBaseModel(type):

    def __init__(cls, name, bases, cls_dict):
        type.__init__(cls, name, bases, cls_dict)

        for key in cls_dict:
            if "build_" in key:
                func = cls_dict[key]
                print(key, func)

                def wrapper(self, *args, **kwargs):
                    self.log(key)
                    return func(self, *args, **kwargs)

                setattr(cls, key, wrapper)
            # new_load = None
            # if 'load' in cls_dict:
            #     def new_load(self, path, limit):
            #         try:
            #             self.if_need_download(path)
            #             cls_dict['load'](self, path, limit)
            #             self.after_load(limit)
            #         except Exception:
            #             exc_type, exc_value, exc_traceback = sys.exc_info()
            #             err_msg = traceback.format_exception(exc_type, exc_value, exc_traceback)
            #             self.log(*err_msg)
            # setattr(cls, 'load', new_load)
        return


META_DATA_FILE_NAME = 'instance.meta'
INSTANCE_FOLDER = 'instance'
VISUAL_RESULT_FOLDER = 'visual_results'


class BaseModel:
    """Abstract class of model for tensorflow graph

    TODO add docstring

    """
    AUTHOR = 'demetoir'

    def __str__(self):
        return "%s_%s" % (self.AUTHOR, self.__class__.__name__)

    def __init__(self, input_shapes=None, params=None, logger_path=None, root_path=ROOT_PATH):
        """create instance of AbstractModel

        :type logger_path: str
        :param logger_path: path for log file
        if logger_path is None, log ony stdout
        """
        self.root_path = root_path
        if logger_path is None:
            self.logger = StdoutOnlyLogger(self.__class__.__name__)
        else:
            self.logger = Logger(self.__class__.__name__, logger_path)
        self.log = self.logger.get_log()

        self.sess = None
        self.saver = None
        self.summary_writer = None
        self.is_built = False

        # gen instance id
        self.input_shapes = input_shapes
        self.params = params

        self.id = self.__str__() + '_' + strftime("%Y_%m_%d_%H_%M_%S", localtime())
        self.instance_path = os.path.join(self.root_path, INSTANCE_FOLDER, self.id)
        self.instance_visual_result_folder_path = os.path.join(self.instance_path, VISUAL_RESULT_FOLDER)
        self.instance_source_folder_path = os.path.join(self.instance_path, 'src_code')
        self.instance_summary_folder_path = os.path.join(self.instance_path, 'summary')
        self.instance_class_name = self.__class__.__name__
        self.instance_source_path = os.path.join(self.instance_source_folder_path, self.id + '.py')
        self.metadata_path = os.path.join(self.instance_path, 'instance.meta')
        self.save_folder_path = os.path.join(self.instance_path, 'check_point')
        self.check_point_path = os.path.join(self.save_folder_path, 'instance.ckpt')

        self.metadata = {
            MODEL_METADATA_KEY_INSTANCE_ID: self.id,
            MODEL_METADATA_KEY_INSTANCE_PATH: self.instance_path,
            MODEL_METADATA_KEY_INSTANCE_VISUAL_RESULT_FOLDER_PATH: self.instance_visual_result_folder_path,
            MODEL_METADATA_KEY_INSTANCE_SOURCE_FOLDER_PATH: self.instance_source_folder_path,
            MODEL_METADATA_KEY_INSTANCE_SOURCE_PATH: self.instance_source_path,
            MODEL_METADATA_KEY_INSTANCE_SUMMARY_FOLDER_PATH: self.instance_summary_folder_path,
            MODEL_METADATA_KEY_INSTANCE_CLASS_NAME: self.instance_class_name,
            MODEL_METADATA_KEY_METADATA_PATH: self.metadata_path,
            MODEL_METADATA_KEY_CHECK_POINT_PATH: self.check_point_path,
            MODEL_METADATA_KEY_SAVE_FOLDER_PATH: self.save_folder_path,
            MODEL_METADATA_KEY_PARAMS: self.params,
            MODEL_METADATA_KEY_INPUT_SHAPES: self.input_shapes,
        }

    def __del__(self):
        """ destructor of InstanceManager

        clean up all memory, subprocess, logging, tensorflow graph
        """
        # reset tensorflow graph
        tf.reset_default_graph()

        self.close_session()

        del self.sess
        del self.root_path
        del self.log
        del self.logger

    @property
    def hyper_param_key(self):
        return []

    def check_setup(self):
        # instance_path = os.path.join(self.root_path, INSTANCE_FOLDER, id)

        if not os.path.exists(self.instance_path):
            return False

        if not os.path.exists(self.instance_visual_result_folder_path):
            return False

        if not os.path.exists(self.instance_source_folder_path):
            return False

        if not os.path.exists(self.instance_summary_folder_path):
            return False

        if not os.path.exists(self.save_folder_path):
            return False
        return True

    def setup_model(self):
        self.log('init directory')
        if not os.path.exists(self.instance_path):
            os.mkdir(self.instance_path)

        if not self.instance_visual_result_folder_path:
            os.mkdir(self.instance_visual_result_folder_path)

        if not os.path.exists(self.instance_source_folder_path):
            os.mkdir(self.instance_source_folder_path)

        if not os.path.exists(self.instance_summary_folder_path):
            os.mkdir(self.instance_summary_folder_path)

        if not os.path.exists(self.save_folder_path):
            os.mkdir(self.save_folder_path)

        # self.log('dump instance source code')
        # try:
        #     copy(inspect.getsourcefile(self.instance_class_name), self.instance_source_path)
        # except IOError as e:
        #     print(e)

    def load_metadata(self, path):
        self.metadata = load_json(path)

        self.id = self.metadata[MODEL_METADATA_KEY_INSTANCE_ID]
        self.instance_path = self.metadata[MODEL_METADATA_KEY_INSTANCE_PATH]
        self.instance_visual_result_folder_path = self.metadata[MODEL_METADATA_KEY_INSTANCE_VISUAL_RESULT_FOLDER_PATH]
        self.instance_source_path = self.metadata[MODEL_METADATA_KEY_INSTANCE_SOURCE_PATH]
        self.instance_class_name = self.metadata[MODEL_METADATA_KEY_INSTANCE_CLASS_NAME]
        self.instance_summary_folder_path = self.metadata[MODEL_METADATA_KEY_INSTANCE_SUMMARY_FOLDER_PATH]
        self.save_folder_path = self.metadata[MODEL_METADATA_KEY_SAVE_FOLDER_PATH]
        self.check_point_path = self.metadata[MODEL_METADATA_KEY_CHECK_POINT_PATH]
        self.params = self.metadata[MODEL_METADATA_KEY_PARAMS]
        self.input_shapes = self.metadata[MODEL_METADATA_KEY_INPUT_SHAPES]

    def save_metadata(self, path):
        self.log('dump metadata')
        dump_json(self.metadata, path)

    def build(self):
        try:
            with tf.variable_scope("misc_ops"):
                self.log("build_misc_ops")
                self.build_misc_ops()

            with tf.variable_scope("hyper_parameter"):
                self.log('build_hyper_parameter')
                self.hyper_parameter()
                self.build_hyper_parameter(self.params)

            self.log('build_input_shapes')
            self.build_input_shapes(self.input_shapes)

            self.log('build_main_graph')
            self.build_main_graph()

            with tf.variable_scope('loss_function'):
                self.log('build_loss_function')
                self.build_loss_function()

            with tf.variable_scope('train_ops'):
                self.log('build_train_ops')
                self.build_train_ops()

            with tf.variable_scope('summary_ops'):
                self.log('build_summary_ops')
                self.build_summary_ops()

        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.log("\n", "".join(traceback.format_tb(exc_traceback)))
            raise ModelBuildFailError("ModelBuildFailError")
        else:
            self.is_built = True
            self.log("build success")

    def open_session(self):
        if self.sess is None:
            self.sess = tf.Session()
            self.saver = tf.train.Saver()
            self.sess.run(tf.global_variables_initializer())
            self.summary_writer = tf.summary.FileWriter(self.instance_summary_folder_path, self.sess.graph)
        else:
            raise Exception("fail to open tf session")

    def close_session(self):
        if self.sess is not None:
            self.sess.close()

        if self.saver is not None:
            self.saver = None

        if self.summary_writer is not None:
            self.summary_writer.close()

    def build_input_shapes(self, input_shapes):
        """load input shapes for tensor placeholder

        :type input_shapes: dict
        :param input_shapes: input shapes for tensor placeholder

        :raise NotImplementError
        if not Implemented
        """
        raise NotImplementedError

    def build_hyper_parameter(self, params=None):
        """load hyper parameter for model

        :param params:
        :raise NotImplementError
        if not implemented
        """
        if params is not None:
            for key in self.hyper_param_key:
                self.__dict__[key] = params[key]

    def build_main_graph(self):
        """load main tensor graph

        :raise NotImplementError
        if not implemented
        """
        raise NotImplementedError

    def build_loss_function(self):
        """load loss function of model

        :raise NotImplementError
        if not implemented
        """
        raise NotImplementedError

    def build_misc_ops(self):
        """load misc operation of model

        :raise NotImplementError
        if not implemented
        """
        self.global_step = tf.get_variable("global_step", shape=1, initializer=tf.zeros_initializer)
        self.op_inc_global_step = tf.assign(self.global_step, self.global_step + 1, name='op_inc_global_step')

        self.global_epoch = tf.get_variable("global_epoch", shape=1, initializer=tf.zeros_initializer)
        self.op_inc_global_step = tf.assign(self.global_epoch, self.global_step + 1, name='op_inc_global_epoch')

    def build_train_ops(self):
        """Load train operation of model

        :raise NotImplementError
        if not implemented
        """
        raise NotImplementedError

    def build_summary_ops(self):
        """load summary operation for tensorboard

        :raise NotImplemented
        if not implemented
        """
        pass

    def write_summary(self, sess=None, iter_num=None, dataset=None, summary_writer=None):
        """write summary of model for tensorboard

        :type sess: Session object for tensorflow.Session
        :type iter_num: int
        :type dataset: dataset_handler.AbstractDataset
        :type summary_writer: tensorflow.summary.FileWriter

        :param sess: session object for tensorflow
        :param iter_num: current iteration number
        :param dataset: dataset for train model
        :param summary_writer: file writer for tensorboard summary

        :raise NotImplementedError
        if not implemented
        """
        pass

    def hyper_parameter(self):
        self.batch_size = None
        pass

    def save(self):
        if not self.check_setup():
            self.setup_model()
            self.save_metadata(self.metadata_path)

        if self.sess is None:
            self.open_session()
        self.saver.save(self.sess, self.check_point_path)

        self.log("saved at {}".format(self.instance_path))

        return self.instance_path

    def load(self, path):
        path = os.path.join(path, 'instance.meta')
        self.load_metadata(path)

        self.build()
        self.close_session()
        self.open_session()

        self.saver.restore(self.sess, self.check_point_path)

    def get_tf_values(self, fetches, feet_dict):
        self.sess.run(fetches, feet_dict)

    def check_build(self):
        pass
