## ADDED Requirements

### Requirement: Multi-channel notification configuration

The notification script SHALL allow users to enable Feishu and Email notifications together by listing both channels in `NOTIFY_CHANNELS`.

#### Scenario: Feishu and Email are enabled together

- **WHEN** `NOTIFY_CHANNELS` is configured as `feishu,email`
- **THEN** the system MUST treat both `feishu` and `email` as enabled notification channels

#### Scenario: Channel list accepts surrounding whitespace

- **WHEN** `NOTIFY_CHANNELS` is configured as `feishu, email`
- **THEN** the system MUST treat both `feishu` and `email` as enabled notification channels

### Requirement: All enabled known channels are attempted

The notification script SHALL attempt to send a notification through every enabled known channel.

#### Scenario: Both Feishu and Email are attempted

- **WHEN** a valid notification event is processed and `NOTIFY_CHANNELS` includes `feishu,email`
- **THEN** the system MUST attempt to send the notification through Feishu
- **THEN** the system MUST attempt to send the notification through Email

### Requirement: Channel failures are isolated

The notification script SHALL isolate failures between enabled channels so one channel failure does not prevent later channels from being attempted.

#### Scenario: Feishu fails before Email

- **WHEN** Feishu sending fails or raises an exception and Email is also enabled
- **THEN** the system MUST still attempt to send the notification through Email
- **THEN** the result summary MUST include a failed result for `feishu`

#### Scenario: Email fails after Feishu

- **WHEN** Feishu succeeds and Email sending fails or raises an exception
- **THEN** the system MUST preserve the successful result for `feishu`
- **THEN** the result summary MUST include a failed result for `email`

### Requirement: Combined Feishu and Email setup is documented

The project documentation SHALL show how to configure Feishu and Email notifications together.

#### Scenario: User configures combined notifications from documentation

- **WHEN** a user reads the environment configuration example or setup documentation
- **THEN** the documentation MUST show `NOTIFY_CHANNELS=feishu,email`
- **THEN** the documentation MUST identify the required Feishu webhook and Email SMTP settings
