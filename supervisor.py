import container
import daemon

class Supervisor:
    def __init__(self, config, client):
        self.client = client
        self.config = config
        self.container = container.Container()
        self.htpc_enabled, self_htpc_binary = config.getHTPCConfig()

    def controlHTPC(self, command):
        try:
            # Some versions of some HTPC software still receive events when they lose focus
            # So let's stop/start the process to get around this.
            pid = int(subprocess.check_output(["pidof", self.htpc_binary]))
            signals = { "stop" : signal.SIGSTOP, "start" : signal.SIGCONT }
            os.kill(pid, signals[command])
        except:
            print("HTPC process not found. Ignoring control command: %s" % command)

    def run(self):
        self.container.setConfig(self.config)
        self.container.buildMounts()
        # self.container.buildWrapper()

        if self.htpc_enabled == True:
            self.controlHTPC("stop")

        # with daemon.DaemonContext():
        self.container.runContainer(self.client)
        # self.monitorContainer(self.container)
        
        if self.htpc_enabled == True:
            self.controlHTPC("start")

