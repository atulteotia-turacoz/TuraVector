/**
 * Ports of templates/documents/terms_and_conditions.html and privacy_policy_standalone.html
 * (the template privacy_policy view renders). Both are standalone public pages; text is verbatim.
 */
import { Link } from 'react-router-dom';
import { CircleCheck, FileText, Info, ShieldCheck } from 'lucide-react';
import { BackButton, BareFrame } from './components';
import './auth.css';

export function TermsPage() {
  return (
    <BareFrame title="Terms and Conditions" right={<BackButton />}>
      <div className="au-legal-wrap">
        <section className="panel">
          <div className="panel-head"><h2 className="row-tight"><FileText size={16} /> TuraVector Terms and Conditions</h2></div>
          <div className="panel-body legal au-legal" style={{ maxWidth: 'none' }}>
            <p className="muted">Last Updated: January 2024</p>

            <h2>1. Acceptance of Terms</h2>
            <p>By accessing and using TuraVector Document Management System ("the Service"), you agree to comply with and be bound by these Terms and Conditions. If you do not agree to these terms, please do not use the Service.</p>

            <h2>2. Service Description</h2>
            <p>TuraVector is a comprehensive document management system designed for healthcare and educational institutions. The Service provides tools for document upload, storage, review, collaboration, and management within a secure environment.</p>

            <h2>3. User Accounts</h2>
            <p>3.1 <strong>Account Creation:</strong> You must provide accurate, complete, and current information during the registration process.</p>
            <p>3.2 <strong>Account Security:</strong> You are responsible for maintaining the confidentiality of your account credentials and for all activities that occur under your account.</p>
            <p>3.3 <strong>Account Types:</strong> Different user types (Manager, Reviewer, User) have different access levels and capabilities within the system.</p>

            <h2>4. Acceptable Use</h2>
            <p>You agree not to:</p>
            <ul>
              <li>Upload or share content that is unlawful, harmful, threatening, abusive, or otherwise objectionable</li>
              <li>Violate any local, state, national, or international law</li>
              <li>Interfere with or disrupt the Service or servers connected to the Service</li>
              <li>Attempt to gain unauthorized access to any portion of the Service</li>
              <li>Use the Service for any unauthorized commercial purpose</li>
            </ul>

            <h2>5. Content Ownership and Rights</h2>
            <p>5.1 <strong>Your Content:</strong> You retain all ownership rights to the documents and content you upload to TuraVector.</p>
            <p>5.2 <strong>License Grant:</strong> By uploading content, you grant TuraVector a limited license to store, process, and display your content solely for the purpose of providing the Service.</p>
            <p>5.3 <strong>Intellectual Property:</strong> You represent that you have the necessary rights to upload and share any content through the Service.</p>

            <h2>6. Privacy and Data Protection</h2>
            <p>Your use of the Service is also governed by our Privacy Policy. We are committed to protecting your personal information and maintaining the confidentiality of all documents stored within the system.</p>

            <h2>7. Document Management Features</h2>
            <p>7.1 <strong>Version Control:</strong> The Service maintains version history for all documents.</p>
            <p>7.2 <strong>Access Control:</strong> Document access is controlled based on user roles and permissions.</p>
            <p>7.3 <strong>Collaboration:</strong> Users may share documents and collaborate according to their assigned permissions.</p>

            <h2>8. Service Availability</h2>
            <p>While we strive to provide uninterrupted access to the Service, we do not guarantee that the Service will be available at all times. We may perform maintenance or updates that could temporarily affect availability.</p>

            <h2>9. Limitation of Liability</h2>
            <p>TuraVector and its affiliates shall not be liable for any indirect, incidental, special, consequential, or punitive damages resulting from your use or inability to use the Service.</p>

            <h2>10. Indemnification</h2>
            <p>You agree to indemnify and hold harmless TuraVector and its affiliates from any claims, damages, or expenses arising from your violation of these Terms and Conditions or your use of the Service.</p>

            <h2>11. Modifications to Terms</h2>
            <p>We reserve the right to modify these Terms and Conditions at any time. Changes will be effective immediately upon posting. Your continued use of the Service constitutes acceptance of the modified terms.</p>

            <h2>12. Termination</h2>
            <p>We may terminate or suspend your account and access to the Service at our sole discretion, without notice, for any reason, including breach of these Terms and Conditions.</p>

            <h2>13. Governing Law</h2>
            <p>These Terms and Conditions shall be governed by and construed in accordance with the laws of the jurisdiction in which TuraVector operates.</p>

            <h2>14. Contact Information</h2>
            <p>For questions about these Terms and Conditions, please contact us through the Help &amp; Support section within the application.</p>

            <div className="notice notice-accent au-legal-note">
              <span className="row-tight" style={{ alignItems: 'flex-start' }}><Info size={14} style={{ marginTop: 3, flex: 'none' }} />
                <span><strong>Note:</strong> By using TuraVector, you acknowledge that you have read, understood, and agree to be bound by these Terms and Conditions.</span></span>
            </div>

            <div className="au-legal-actions">
              <BackButton label="Back to Application" className="btn btn-primary" />
            </div>
          </div>
        </section>
      </div>
    </BareFrame>
  );
}

export function PrivacyPolicyPage() {
  return (
    <BareFrame title="Privacy Policy" right={<BackButton />}>
      <div className="au-legal-wrap">
        <section className="panel">
          <div className="panel-head"><h2 className="row-tight"><ShieldCheck size={16} /> TuraVector Privacy Policy</h2></div>
          <div className="panel-body legal au-legal" style={{ maxWidth: 'none' }}>
            <p className="muted">Last Updated: January 2024</p>

            <div className="notice notice-accent">
              <span className="row-tight" style={{ alignItems: 'flex-start' }}><ShieldCheck size={14} style={{ marginTop: 3, flex: 'none' }} />
                <span><strong>Your Privacy Matters:</strong> TuraVector is committed to protecting your personal information and your right to privacy.</span></span>
            </div>

            <h2>1. Information We Collect</h2>
            <p>We collect information that you provide directly to us, including:</p>
            <ul>
              <li><strong>Account Information:</strong> Name, email address, password, and user type</li>
              <li><strong>Profile Information:</strong> Professional details, institution affiliation, and contact information</li>
              <li><strong>Document Data:</strong> Files, documents, and content you upload to the system</li>
              <li><strong>Usage Information:</strong> How you interact with our Service, including access times and features used</li>
              <li><strong>Communication Data:</strong> Messages, feedback, and support requests</li>
            </ul>

            <h2>2. How We Use Your Information</h2>
            <p>We use the collected information for the following purposes:</p>
            <ul>
              <li>Provide, maintain, and improve the Service</li>
              <li>Process and complete transactions</li>
              <li>Send administrative information and updates</li>
              <li>Respond to comments, questions, and support requests</li>
              <li>Monitor and analyze usage patterns and trends</li>
              <li>Ensure security and prevent fraud</li>
              <li>Comply with legal obligations</li>
            </ul>

            <h2>3. Data Storage and Security</h2>
            <p>3.1 <strong>Storage:</strong> Your data is stored on secure servers with encryption at rest and in transit.</p>
            <p>3.2 <strong>Access Control:</strong> We implement strict access controls to ensure only authorized personnel can access user data.</p>
            <p>3.3 <strong>Security Measures:</strong> We employ industry-standard security measures including:</p>
            <ul>
              <li>SSL/TLS encryption for data transmission</li>
              <li>Regular security audits and assessments</li>
              <li>Secure password policies and multi-factor authentication options</li>
              <li>Regular backups and disaster recovery procedures</li>
            </ul>

            <h2>4. Document Privacy</h2>
            <p>4.1 <strong>Document Confidentiality:</strong> All documents uploaded to TuraVector remain confidential and are only accessible to authorized users.</p>
            <p>4.2 <strong>Access Permissions:</strong> Document access is strictly controlled based on user roles and sharing permissions.</p>
            <p>4.3 <strong>Version History:</strong> We maintain version history securely, with access limited to authorized users.</p>

            <h2>5. Data Sharing and Disclosure</h2>
            <p>We do not sell, trade, or rent your personal information. We may share information only in the following circumstances:</p>
            <ul>
              <li><strong>With Your Consent:</strong> When you explicitly authorize us to share information</li>
              <li><strong>Within Your Organization:</strong> With other authorized users in your institution as per access permissions</li>
              <li><strong>Service Providers:</strong> With trusted third parties who assist in operating our Service</li>
              <li><strong>Legal Requirements:</strong> When required by law or to protect rights and safety</li>
            </ul>

            <h2>6. Data Retention</h2>
            <p>We retain your information for as long as your account is active or as needed to provide services. You may request deletion of your data at any time, subject to legal and contractual obligations.</p>

            <h2>7. Your Rights and Choices</h2>
            <p>You have the following rights regarding your personal information:</p>
            <ul>
              <li><strong>Access:</strong> Request access to your personal information</li>
              <li><strong>Update:</strong> Correct or update your information through your profile</li>
              <li><strong>Delete:</strong> Request deletion of your account and associated data</li>
              <li><strong>Export:</strong> Request a copy of your data in a portable format</li>
              <li><strong>Opt-out:</strong> Unsubscribe from non-essential communications</li>
            </ul>

            <h2>8. Cookies and Tracking</h2>
            <p>We use cookies and similar technologies to maintain session state, remember preferences, and analyze usage. You can control cookie settings through your browser preferences.</p>

            <h2>9. Children's Privacy</h2>
            <p>TuraVector is not intended for use by children under 18 years of age. We do not knowingly collect personal information from children.</p>

            <h2>10. International Data Transfers</h2>
            <p>If you access TuraVector from outside our primary operating jurisdiction, your information may be transferred and processed in different countries. We ensure appropriate safeguards are in place for such transfers.</p>

            <h2>11. Updates to This Policy</h2>
            <p>We may update this Privacy Policy periodically. We will notify you of any material changes through the Service or via email. Your continued use after such modifications constitutes acceptance of the updated policy.</p>

            <h2>12. Data Breach Notification</h2>
            <p>In the event of a data breach that may affect your personal information, we will notify affected users promptly in accordance with applicable laws and regulations.</p>

            <h2>13. Contact Information</h2>
            <p>For privacy-related questions or concerns, please contact us through:</p>
            <ul>
              <li>The Help &amp; Support section within the application</li>
              <li>Your designated system administrator</li>
            </ul>

            <h2>14. Compliance</h2>
            <p>TuraVector is designed to comply with applicable data protection regulations including GDPR, HIPAA (where applicable), and other relevant privacy laws.</p>

            <div className="notice notice-ok au-legal-note">
              <span className="row-tight" style={{ alignItems: 'flex-start' }}><CircleCheck size={14} style={{ marginTop: 3, flex: 'none' }} />
                <span><strong>Our Commitment:</strong> We are dedicated to maintaining the trust you place in us by protecting your privacy and securing your data.</span></span>
            </div>

            <div className="au-legal-actions">
              <BackButton label="Back to Application" className="btn btn-primary" />
              <Link to="/documents/terms-and-conditions/" className="btn btn-secondary"><FileText size={14} /> View Terms &amp; Conditions</Link>
            </div>
          </div>
        </section>
      </div>
    </BareFrame>
  );
}

