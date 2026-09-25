# Front-end & API Integration
This folder contains the JavaScript code for integration with the Dial Forge APIs (HubSpot, Apollo.io, Zendesk, and Zapier).
This document details how the front-end is utilizing the APIs and how the data is being displayed on the front-end. 

## Pages that utilize the APIs
| Page | API | Description |
|------|-----|-------------|
| Dashboard | &bull; HubSpot<br>&bull; Zendesk | &bull; Hubspot: to get the total number of contacts, recent contacts, and contact-related metrics<br>&bull; Zendesk: to get ticket information |
| Active Call | &bull; HubSpot | &bull; HubSpot: to get contact information when a call connects to enrich the CRM panel and adds the contacts information to HubSpot if the search fails |
| Power Dialer | &bull; HubSpot | &bull; to get matching contact information to enrich the Active Call workflow and to save the contacts information in HubSpot |
| Notifications | &bull; Zapier<br>&bull; Zendesk | &bull; Zapier: to get incoming webhook events and turn them into notifications<br>&bull; Zendesk: to get ticket information and turn them into notifications |
| Profile | &bull; HubSpot<br>&bull; Zendesk | &bull; HubSpot: to get the CRM sync status and lifecycle stage<br>Zendesk: to get ticket history |
| Post Call Summary | &bull; Zendesk<br>&bull; HubSpot<br>&bull; Zapier | &bull; Zendesk: to convert the call into a support ticket if needed<br>&bull; HubSpot: to update the CRM with call outcome<br>&bull; Zapier: to send call summary to external systems (Slack, email, etc.) |
| Sales Pipeline | &bull; HubSpot<br>&bull; Apollo.io | &bull; HubSpot: to sync deals, deal stages, and pipeline performance metrics<br>&bull; Apollo.io: to track prospect status within active sales sequences |
| Contacts | &bull; HubSpot<br>&bull; Apollo.io | &bull; HubSpot: to sync contact records, custom attributes, and lifecycle stages<br>&bull; Apollo.io: to enrich contact details and sync lead lists
| Call History | &bull; Dial Forge API<br>• HubSpot<br>&bull; Zendesk | &bull; Dial Forge API: to fetch call logs, call durations, and audio recordings<br>&bull; HubSpot/Zendesk: to sync call activity records directly to CRM contacts and support tickets
| Support Queue | &bull; Zendesk | &bull; Zendesk: to retrieve active support ticket queues, attach incoming calls to tickets, and track agent ticket metrics |
| Coaching | &bull; Dial Forge API<br>&bull; HubSpot | &bull; Dial Forge API: to enable live call monitoring (whisper/barge) and fetch call recording scorecards<br>&bull; HubSpot: to sync rep performance and coaching metrics |
| Integrations | &bull; HubSpot<br>&bull; Apollo.io<br>&bull; Zendesk<br>&bull; Zapier | &bull; All APIs: to manage OAuth connections, authentication tokens, webhooks, and integration status across third-party platforms |
| Numbers | &bull; Dial Forge API | &bull; to provision, assign, purchase, and configure virtual phone numbers and caller ID profiles |
| Billing | &bull; Dial Forge API | &bull; to manage workspace subscription plans, view invoice history, track credit usage, and update payment methods |
| Team Governance | &bull; Dial Forge API | &bull; to manage workspace hierarchy, domain verification settings, and organization-wide security policies |
| Team Roles | &bull; Dial Forge API | &bull; to configure role-based access control (RBAC), custom role permissions, and user group assignments |
| Settings General | &bull; Dial Forge API | &bull; to manage company profile details, workspace timezones, business hours, and default system settings |
| Calling Configuration | &bull; Dial Forge API | &bull; to manage WebRTC audio device settings, call routing rules, voicemail drop audio, and power dialer defaults |
| Calling Compliance | &bull; Dial Forge API | &bull; to manage Do Not Call (DNC) lists. STIR/SHAKEN registration. call recording consent requirements. and compliance audit logs |
| Security SSO | &bull; Dial Forge API | &bull; to configure Single Sign-On (SSO / SAML 2.0 / OAuth), enforce two-factor authentication (2FA), and manage active sessions |
| API | &bull; Dial Forge API<br>&bull; Zapier | &bull; Dial Forge API: to generate and revoke API keys and view rate limits<br>• Zapier: to configure custom incoming and outgoing webhook endpoints |
| Notification Settings | &bull; Zapier<br>• Dial Forge API | &bull; Zapier: to trigger event notifications to external services (Slack, email, SMS)<br>&bull; Dial Forge API: to manage in-app and desktop alert preferences |


Note: The pages that have DialForge API listed as the API are the pages that need to have backend access to get user information.