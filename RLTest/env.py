# coding=utf-8
from __future__ import print_function
import os
import sys
import redis
import unittest
import inspect
import contextlib
import warnings
from .redis_std import StandardEnv
from .redis_cluster import ClusterEnv
from .utils import Colors
from .Enterprise import EnterpriseClusterEnv
from .exists_redis import ExistsRedisEnv
from .redis_enterprise_cluster import EnterpriseRedisClusterEnv


class TestAssertionFailure(Exception):
    pass


def genDeprecated(name, target):
    def method(*argc, **nargs):
        warnings.warn('%s is deprecated, use %s instead' % (str(name), str(target)), DeprecationWarning)
        return target(*argc, **nargs)
    return method


class Query:
    def __init__(self, env, *query):
        self.query = query
        self.env = env
        self.errorRaised = False
        self._evaluate()

    def _evaluate(self):
        try:
            self.res = self.env.cmd(*self.query)
        except Exception as e:
            self.res = str(e)
            self.errorRaised = True

    def _prettyPrint(self, result, prefix='\t'):
        if type(result) is list:
            print(prefix + '[')
            for r in result:
                self._prettyPrint(r, prefix + '\t')
            print(prefix + ']')
            return
        print(prefix + str(result))

    def prettyPrint(self):
        self._prettyPrint(self.res)
        return self

    def debugPrint(self):
        self.env.debugPrint('query: %s, result: %s' % (self.query, self.res), force=True)
        return self

    def equal(self, expected):
        self.env.assertEqual(self.res, expected, 1)
        return self

    def noEqual(self, expected):
        self.env.assertNotEqual(self.res, expected, 1)
        return self

    def true(self):
        self.env.assertTrue(self.res, 1)
        return self

    def false(self):
        self.env.assertFalse(self.res, 1)
        return self

    def ok(self):
        self.env.assertEqual(self.res, 'OK', 1)
        return self

    def contains(self, val):
        self.env.assertContains(val, self.res, 1)
        return self

    def notContains(self, val):
        self.env.assertNotContains(val, self.res, 1)
        return self

    def error(self):
        self.env.assertTrue(self.errorRaised, 1)
        return self

    def noError(self):
        self.env.assertFalse(self.errorRaised, 1)
        return self

    raiseError = genDeprecated('raiseError', error)
    notRaiseError = genDeprecated('notRaiseError', noError)


class Defaults:
    module = None
    module_args = []

    env = 'oss'
    binary = 'redis-server'
    proxy_binary = None
    re_binary = None
    re_libdir = None
    use_aof = False
    debugger = None
    debug_print = False
    debug_pause = False
    no_capture_output = False
    exit_on_failure = False
    verbose = 0
    logdir = None
    use_slaves = False
    num_shards = 1
    external_addr = 'localhost:6379'
    use_unix = False
    randomize_ports = False


class Env:
    RTestInstance = None
    EnvCompareParams = ['module', 'moduleArgs', 'env', 'useSlaves', 'shardsCount', 'useAof']

    def compareEnvs(self, env):
        if env is None:
            return False
        for param in Env.EnvCompareParams:
            if self.__dict__[param] != env.__dict__[param]:
                return False
        return True

    def __init__(self, testName=None, testDescription=None, module=None, moduleArgs=None, env=None, useSlaves=None, shardsCount=None,
                 useAof=None):
        self.testName = testName if testName else '%s.%s' % (inspect.getmodule(inspect.currentframe().f_back).__name__, inspect.currentframe().f_back.f_code.co_name)
        self.testName = self.testName.replace(' ', '_')

        if testDescription:
            print(Colors.Gray('\tdescription: ' + testDescription))

        self.module = module if module else Defaults.module
        self.moduleArgs = moduleArgs if moduleArgs else Defaults.module_args
        self.env = env if env else Defaults.env
        self.useSlaves = useSlaves if useSlaves else Defaults.use_slaves
        self.shardsCount = shardsCount if shardsCount else Defaults.num_shards
        self.useAof = useAof if useAof else Defaults.use_aof
        self.verbose = Defaults.verbose
        self.logDir = Defaults.logdir

        self.assertionFailedSummary = []

        if Env.RTestInstance.currEnv and self.compareEnvs(Env.RTestInstance.currEnv):
            self.envRunner = Env.RTestInstance.currEnv.envRunner
        else:
            if Env.RTestInstance.currEnv:
                Env.RTestInstance.currEnv.stop()
            self.envRunner = self.getEnvByName()

        try:
            os.makedirs(self.logDir)
        except Exception:
            pass

        self.start()
        if self.verbose >= 2:
            print(Colors.Blue('\tenv data:'))
            self.envRunner.printEnvData('\t\t')

        Env.RTestInstance.currEnv = self

        if Defaults.debug_pause:
            raw_input('\tenv is up, attach to any process with gdb and press any button to continue.')

    def getEnvByName(self):
        kwargs = {
            'modulePath': self.module,
            'moduleArgs': self.moduleArgs,
            'useSlaves': self.useSlaves,
            'useAof': self.useAof,
            'dbDirPath': self.logDir,
            'debugger': Defaults.debugger,
            'noCatch': Defaults.no_capture_output
        }

        single_args = {}
        if Defaults.randomize_ports:
            single_args['port'] = 0
        if Defaults.use_unix:
            single_args['unix'] = True

        if self.env == 'oss':
            kwargs.update(single_args)
            return StandardEnv(redisBinaryPath=Defaults.binary,
                               outputFilesFormat='%s-' + '%s-oss' % self.testName,
                               **kwargs)
        if self.env == 'enterprise':
            kwargs.update(single_args)
            kwargs['libPath'] = Defaults.re_libdir
            return StandardEnv(redisBinaryPath=Defaults.re_binary,
                               outputFilesFormat='%s-' + '%s-oss' % self.testName,
                               **kwargs)
        if self.env == 'enterprise-cluster':
            kwargs['libPath'] = Defaults.re_libdir
            return EnterpriseClusterEnv(shardsCount=self.shardsCount,
                                        redisBinaryPath=Defaults.re_binary,
                                        outputFilesFormat='%s-' + '%s-re-cluster' % self.testName,
                                        dmcBinaryPath=Defaults.proxy_binary,
                                        **kwargs)
        if self.env == 'oss-cluster':
            return ClusterEnv(shardsCount=self.shardsCount, redisBinaryPath=Defaults.binary,
                              outputFilesFormat='%s-' + '%s-oss-cluster' % self.testName,
                              randomizePorts=Defaults.randomize_ports,
                              **kwargs)

        if self.env == 'existing-env':
            return ExistsRedisEnv(addr=Defaults.external_addr, **kwargs)

        if self.env == 'cluster_existing-env':
            return EnterpriseRedisClusterEnv(addr = Defaults.external_addr, password = Defaults.internal_password,
                                             shards_port=Defaults.shards_ports, **kwargs)

    def start(self):
        self.envRunner.startEnv()
        self.con = self.getConnection()

    def stop(self):
        self.envRunner.stopEnv()

    def getEnvStr(self):
        return self.env

    def getConnection(self, shardId=1):
        return self.envRunner.getConnection(shardId)

    def getSlaveConnection(self):
        return self.envRunner.getSlaveConnection()

    def flush(self):
        self.envRunner.flush()

    def isCluster(self):
        return 'cluster' in self.env

    def isEnterpiseCluster(self):
        return isinstance(self.envRunner, EnterpriseRedisClusterEnv)

    def _getCallerPosition(self, back_frames):
        frame = inspect.currentframe()
        while frame and back_frames > 0:
            back_frames -= 1
            frame = frame.f_back
        if frame:
            return '%s:%s' % (
                os.path.basename(frame.f_code.co_filename),
                frame.f_lineno)

    def _assertion(self, checkStr, trueValue, depth=0, message=None):
        basemsg = Colors.Yellow(checkStr) + '\t' + Colors.Gray(self._getCallerPosition(3 + depth))
        if message:
            basemsg += ' [{}]'.format(message)

        if trueValue and self.verbose:
            print('\t' + Colors.Green('✅  (OK):\t') + basemsg)
        elif not trueValue:
            failureSummary = Colors.Bred('❌  (FAIL):\t') + basemsg
            print('\t' + failureSummary)
            if Defaults.exit_on_failure:
                raise TestAssertionFailure('Assertion Failed!')

            self.assertionFailedSummary.append(failureSummary)

    def getNumberOfFailedAssertion(self):
        return len(self.assertionFailedSummary)

    def assertEqual(self, first, second, depth=0, message=None):
        self._assertion('%s == %s' % (repr(first), repr(second)), first == second, depth, message=message)

    def assertNotEqual(self, first, second, depth=0, message=None):
        self._assertion('%s != %s' % (repr(first), repr(second)), first != second, depth, message=message)

    def assertOk(self, val, depth=0, message=None):
        self.assertEqual(val, 'OK', depth + 1, message=message)

    def assertTrue(self, val, depth=0, message=None):
        self.assertEqual(bool(val), True, depth + 1, message=message)

    def assertFalse(self, val, depth=0, message=None):
        self.assertEqual(bool(val), False, depth + 1, message=message)

    def assertContains(self, value, holder, depth=0):
        self._assertion('%s should contains %s' % (repr(holder), repr(value)), value in holder, depth)

    def assertNotContains(self, value, holder, depth=0):
        self._assertion('%s should not contains %s' % (repr(holder), repr(value)), value not in holder, depth)

    def assertGreaterEqual(self, value1, value2, depth=0):
        self._assertion('%s >= %s' % (repr(value1), repr(value2)), value1 >= value2, depth)

    def assertGreater(self, value1, value2, depth=0):
        self._assertion('%s > %s' % (repr(value1), repr(value2)), value1 > value2, depth)

    def assertLessEqual(self, value1, value2, depth=0):
        self._assertion('%s <= %s' % (repr(value1), repr(value2)), value1 <= value2, depth)

    def assertLess(self, value1, value2, depth=0):
        self._assertion('%s < %s' % (repr(value1), repr(value2)), value1 < value2, depth)

    def assertIsNotNone(self, value, depth=0):
        self._assertion('%s is not None' % (repr(value)), value is not None, depth)

    def assertIsNone(self, value, depth=0):
        self._assertion('%s is None' % (repr(value)), value is None, depth)

    def assertIsInstance(self, value, instance, depth=0):
        self._assertion('%s instance of %s' % (repr(value), repr(instance)), isinstance(value, instance), depth)

    def assertAlmostEqual(self, value1, value2, delta, depth=0):
        self._assertion('%s almost equels %s (delta %s)' % (repr(value1), repr(value2), repr(delta)), abs(value1 - value2) <= delta, depth)

    def expect(self, *query):
        return Query(self, *query)

    def cmd(self, *query):
        res = self.con.execute_command(*query)
        self.debugPrint('query: %s, result: %s' % (repr(query), repr(res)))
        return res

    def assertCmdOk(self, cmd, *args, **kwargs):
        self.assertOk(self.cmd(cmd, *args, **kwargs))

    def exists(self, val):
        warnings.warn("Exists is deprecated, use cmd instead", DeprecationWarning)
        return self.envRunner.exists(val)

    def assertExists(self, val, depth=0):
        warnings.warn("AssertExists is deprecated, use cmd instead", DeprecationWarning)
        self._assertion('%s exists in db' % repr(val), self.con.exists(val), depth=0)

    def executeCommand(self, *query):
        warnings.warn("execute_command is deprecated, use cmd instead", DeprecationWarning)
        return self.cmd(*query)

    def reloadingIterator(self):
        yield 1
        self.dumpAndReload()
        yield 2

    def dumpAndReload(self, restart=False, shardId=None):
        self.envRunner.dumpAndReload(restart=restart, shardId=shardId)

    def hmset(self, *args):
        warnings.warn("hmset is deprecated, use Cmd instead", DeprecationWarning)
        return self.envRunner.hmset(*args)

    def keys(self, reg):
        warnings.warn("keys is deprecated, use Cmd instead", DeprecationWarning)
        return self.envRunner.keys(reg)

    def assertRaises(self, var1, var2, *query):
        warnings.warn("assertRaises is deprecated, use Expect + RaiseError instead", DeprecationWarning)
        self.expect(*query).raiseError()

    @contextlib.contextmanager
    def assertResponseError(self, msg=None, contained=None):
        """
        Assert that a context block with a redis command triggers a redis error response.

        For Example:

            with self.assertResponseError():
                r.execute_command('non_existing_command')
        """

        warnings.warn("assertResponseError is deprecated, use Expect + RaiseError instead", DeprecationWarning)

        try:
            yield 1
        except Exception as e:
            if contained:
                self.assertContains(contained, str(e), depth=2)
            self._assertion('Expected Response Error', True, depth=1)
        else:
            self._assertion('Expected Response Error', False, depth=1)

    def restartAndReload(self, shardId=None):
        self.dumpAndReload(restart=True, shardId=shardId)

    def broadcast(self, *cmd):
        self.envRunner.broadcast(*cmd)

    def debugPrint(self, msg, force=False):
        if Defaults.debug_print or force:
            print('\t' + Colors.Bold('debug:\t') + Colors.Gray(msg))

    def checkExitCode(self):
        return self.envRunner.checkExitCode()

    def isUp(self):
        return self.envRunner.isUp()

    def skip(self):
        raise unittest.SkipTest()

    def skipOnCluster(self):
        if self.isCluster():
            self.skip()

    def skipOnEnterpriseCluster(self):
        if self.isEnterpiseCluster():
            self.skip()

    _mm = {
        'assertEquals': assertEqual,
        'assertListEqual': assertEqual,
        'retry_with_reload': reloadingIterator,
        'retry_with_rdb_reload': reloadingIterator,
        'reloading_iterator': reloadingIterator,
        'dump_and_reload': dumpAndReload,
        'restart_and_reload': restartAndReload,
        'execute_command': cmd,
        'assertIn': assertContains,
        'assertNotIn': assertNotContains,
        'is_cluster': isCluster,
        'is_enterprise_redis_clusterEnv':isEnterpiseCluster
    }
    for k, v in _mm.items():
        locals().update({k:genDeprecated(k, v)})
