import Foundation
import Capacitor
import AVFoundation
import UIKit

@objc(AnyqNativePlugin)
public class AnyqNativePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "AnyqNativePlugin"
    public let jsName = "AnyqNative"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "requestMicrophone", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openExternal", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "saveFile", returnType: CAPPluginReturnPromise)
    ]

    @objc func requestMicrophone(_ call: CAPPluginCall) {
        AVAudioSession.sharedInstance().requestRecordPermission { granted in
            call.resolve(["granted": granted])
        }
    }

    @objc func openExternal(_ call: CAPPluginCall) {
        guard let raw = call.getString("url"), let url = URL(string: raw),
              let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http" else {
            call.reject("Only http(s) URLs can be opened")
            return
        }
        DispatchQueue.main.async {
            UIApplication.shared.open(url, options: [:]) { ok in
                if ok {
                    call.resolve()
                } else {
                    call.reject("Could not open the link")
                }
            }
        }
    }

    @objc func saveFile(_ call: CAPPluginCall) {
        guard let filename = call.getString("filename"),
              let data = call.getString("data"),
              let bytes = Data(base64Encoded: data) else {
            call.reject("filename and data are required")
            return
        }
        let safe = filename
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "..", with: "_")
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let file = dir.appendingPathComponent(safe.isEmpty ? "download" : safe)
        do {
            try bytes.write(to: file, options: .atomic)
        } catch {
            call.reject("Could not write the file")
            return
        }
        DispatchQueue.main.async {
            let controller = UIActivityViewController(activityItems: [file], applicationActivities: nil)
            if let popover = controller.popoverPresentationController {
                popover.sourceView = self.bridge?.viewController?.view
                popover.sourceRect = CGRect(x: UIScreen.main.bounds.midX, y: UIScreen.main.bounds.midY, width: 0, height: 0)
            }
            self.bridge?.viewController?.present(controller, animated: true) {
                call.resolve(["uri": file.absoluteString])
            }
        }
    }
}
