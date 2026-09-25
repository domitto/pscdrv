#!../../bin/linux-x86_64/pscdemo

## Register all support components
dbLoadDatabase("../../dbd/pscdemo.dbd",0,0)
pscdemo_registerRecordDeviceDriver(pdbbase)

dbLoadRecords("sim.db","P=TST:,NAME=thesim")

createPSC("thesim", "localhost", 5678, 1)
setPSCSendBlockSize("thesim", 1, 4)
setPSCSendBlockSize("thesim", 2, 4) # Period-SP

iocInit()

# let the connection settle, then tell the (simulated) device to turn the
# beam on and auto-toggle source A/B - this is a real write, over the
# network, to the simulator, not a local database trick
epicsThreadSleep(1)
dbpf("TST:BEAM", "1")
dbpf("TST:AUTO", "1")
dbpf("TST:Period-SP", "100")
