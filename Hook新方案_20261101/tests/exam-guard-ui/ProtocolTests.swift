import Foundation

@main struct ProtocolTests {
    static var checks = 0
    static func expect(_ condition: @autoclosure () -> Bool, _ label: String) {
        checks += 1
        if !condition() { fputs("FAIL: \(label)\n", stderr); exit(1) }
    }
    static func message(_ seq: Int, state: String = "ready", allowed: Bool = false, health: String = "healthy", extra: [String: Any] = [:]) -> Data {
        var d: [String: Any] = ["protocolVersion": 1, "type": "status", "sessionID": "test-session",
                               "sequence": seq, "state": state, "canStart": state == "ready", "examAllowed": allowed,
                               "health": health, "message": "synthetic status"]
        for (k,v) in extra { d[k] = v }
        return try! JSONSerialization.data(withJSONObject: d)
    }
    static func main() throws {
        let continuousBefore = ExamGuardClock.now()
        let continuousAfter = ExamGuardClock.now()
        expect(continuousBefore.isFinite && continuousAfter >= continuousBefore, "continuous clock is available and monotonic")
        var gate = ExamGuardGate(sessionID: "test-session")
        expect(!gate.showQuestions(at: 0), "initial closed")
        expect(!gate.canStart(at: 0), "initial cannot start")
        try gate.accept(message(1), now: 1)
        expect(gate.canStart(at: 1), "ready enables start")
        expect(!gate.showQuestions(at: 1), "ready does not expose questions")
        try gate.accept(message(2,state:"exam",allowed:true), now: 1.5)
        expect(!gate.showQuestions(at: 1.5), "unsolicited exam cannot open gate")
        gate.requestStart()
        try gate.accept(message(3,state:"exam",allowed:true), now: 2)
        expect(gate.showQuestions(at: 2), "local start plus fresh permission opens")
        expect(!gate.showQuestions(at: 5), "stale heartbeat closes")
        try gate.accept(message(4,state:"exam",allowed:true), now: 6)
        expect(!gate.showQuestions(at: 6), "late message cannot silently resume")
        expect(gate.canResume(at: 6), "late valid exam requires explicit resume")
        gate.requestStart()
        try gate.accept(message(5,state:"exam",allowed:true), now: 6.1)
        expect(gate.showQuestions(at: 6.1), "explicit resume works")
        do { try gate.accept(message(5,state:"exam",allowed:true), now: 6.2); expect(false,"replay accepted") }
        catch { expect(!gate.showQuestions(at: 6.2), "replay closes gate") }
        try gate.accept(message(6,state:"exam",allowed:true), now: 6.3)
        expect(!gate.showQuestions(at: 6.3), "fresh replay recovery cannot auto resume")
        gate.requestStart()
        try gate.accept(message(7,state:"exam",allowed:true), now: 6.4)
        gate.requestEnd()
        expect(!gate.showQuestions(at: 6.4), "end hides immediately")
        try gate.accept(message(8,state:"exam",allowed:true), now: 6.5)
        gate.requestStart()
        expect(!gate.showQuestions(at: 6.5), "late exam or start cannot undo end")
        for bad: [String: Any] in [
            ["sessionID":"different"], ["protocolVersion":true], ["sequence":true], ["sequence":1.5],
            ["canStart":1], ["examAllowed":"true"], ["state":"unknown"], ["type":"event"],
            ["canStart":true,"health":"unhealthy"], ["examAllowed":true], ["message":42]
        ] {
            var badGate = ExamGuardGate(sessionID:"test-session")
            do { try badGate.accept(message(1,extra:bad),now:0); expect(false,"invalid typed/status accepted: \(bad)") }
            catch { expect(!badGate.showQuestions(at:0),"invalid record closed") }
        }
        var paused = ExamGuardGate(sessionID:"test-session")
        try paused.accept(message(1),now:1); paused.requestStart()
        try paused.accept(message(2,state:"exam",allowed:true),now:1.1)
        try paused.accept(message(3,state:"paused"),now:1.2)
        expect(!paused.showQuestions(at:1.2),"paused hides")
        try paused.accept(message(4,state:"exam",allowed:true),now:1.3)
        expect(!paused.showQuestions(at:1.3),"paused cannot auto resume")
        try paused.accept(message(5,state:"paused"),now:1.4)
        paused.requestStart()
        try paused.accept(message(6,state:"paused"),now:1.5)
        expect(!paused.showQuestions(at:1.5),"pending resume still hides")
        try paused.accept(message(7,state:"exam",allowed:true),now:1.6)
        expect(paused.showQuestions(at:1.6),"healthy paused heartbeat does not discard explicit resume")
        var backwards = ExamGuardGate(sessionID:"test-session")
        try backwards.accept(message(1),now:3); backwards.requestStart()
        try backwards.accept(message(2,state:"exam",allowed:true),now:4)
        try backwards.accept(message(3,state:"exam",allowed:true),now:2)
        expect(!backwards.showQuestions(at:2),"backward clock clears local permit")
        let report: [String:Any] = ["testKind":"pure_protocol_and_gate", "checks":checks,"passed":true,
                                   "actualRemoteTerminationTested":false]
        let data = try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys])
        print(String(data:data,encoding:.utf8)!)
    }
}
