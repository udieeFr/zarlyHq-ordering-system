import sys
import os
from pyhanko.sign import validation
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko_certvalidator import ValidationContext
from asn1crypto import x509, pem

def verify_pdf_integrity(pdf_path):
    """
    Verifies that a Zarly Order Receipt has a valid digital signature
    and has NOT been tampered with.
    """
    print(f"\n🔍 STARTING INTEGRITY CHECK FOR: {pdf_path}")
    print("=" * 60)

    # 1. Check if PDF file exists
    if not os.path.exists(pdf_path):
        print(f" ERROR: File not found at {pdf_path}")
        return

    # 2. Define the 'Trusted Authority'
    # cari certificates
    cert_path = os.path.join('secure_keys', 'zarly_cert.pem')
    
    if not os.path.exists(cert_path):
        print(" CRITICAL: 'zarly_cert.pem' not found in secure_keys folder.")
        return

    # 3. Load the Certificate (Robust PEM/DER handling)
    try:
        with open(cert_path, 'rb') as f:
            cert_data = f.read()
            
            # Check if it is a PEM (Text) file and unwrap it if necessary
            if pem.detect(cert_data):
                _, _, cert_bytes = pem.unarmor(cert_data)
                trusted_cert = x509.Certificate.load(cert_bytes)
            else:
                # Assume it is already binary (DER)
                trusted_cert = x509.Certificate.load(cert_data)
                
    except Exception as e:
        print(f" ERROR: Could not load the certificate file. {e}")
        return

    # 4. Create a Trust Context 
    # get public key daripada certificate
    trust_context = ValidationContext(trust_roots=[trusted_cert])

    try:
        with open(pdf_path, 'rb') as doc:
            r = PdfFileReader(doc)
            
            # 5. Find all signatures
            sig_positions = r.embedded_signatures
            if not sig_positions:
                print("  RESULT: No digital signature found in this PDF.")
                return

            print(f"ℹ  Found {len(sig_positions)} signature(s). Verifying...\n")

            for i, sig in enumerate(sig_positions):
                # 6. Validate (UPDATED PARAMETER NAME)
                status = validation.validate_pdf_signature(
                    sig, 
                    signer_validation_context=trust_context  # <--- FIXED HERE
                )
                
                print(f"--- Signature #{i+1} Analysis ---")

                #check signature siapa
                try:
                    # Safely get the name
                    signer_name = status.signing_cert.subject.human_friendly
                except:
                    signer_name = "Unknown Signer"
                    
                print(f"   • Signed By: {signer_name}")
                print(f"   • Timestamp: {status.signer_reported_dt}")
                
                # CHECK can decrypt or not
                if status.valid:
                    print("   • Crypto Check:  VALID (Signature matches Public Key)")
                else:
                    print("   • Crypto Check:  INVALID (Fake or Broken Signature)")

                # CHECK temper status
                if status.intact:
                    print("   • Integrity:     INTACT (Document has NOT been modified)")
                else:
                    print("   • Integrity:     TAMPERED (Document was changed after signing!)")

                print("-" * 30)
                
                # Final Verdict
                if status.valid and status.intact:
                    print(f"\n VERDICT: This is an AUTHENTIC Zarly Receipt.")
                else:
                    print(f"\n VERDICT: This receipt is INVALID or TAMPERED.")

    except Exception as e:
        print(f" ERROR during verification: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        target_file = input("Enter path to PDF: ")
    
    verify_pdf_integrity(target_file)