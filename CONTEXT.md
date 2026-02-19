# Careerk Platform - CV Parsing Context

## Project Overview

**Careerk** is a full-stack job platform connecting job seekers with employers. The platform allows job seekers to create profiles, upload CVs, and apply to jobs. Companies can post jobs, search for candidates, and manage applications.

The Python NLP service will:

1. Receive a CV URL (typically a presigned S3/minio URL)
2. Download the CV file (PDF, DOCX formats)
3. Parse the CV using NLP to extract structured data
4. Populate the database with extracted information

---

## Database Schema

### JobSeeker (User Account)

```typescript
{
  id: string (UUID)
  email: string (unique)
  password: string
  firstName: string
  lastName: string
  profileImageUrl?: string
  isActive: boolean (default: true)
  isVerified: boolean (default: false)
  lastLoginAt?: DateTime
  createdAt: DateTime
  updatedAt: DateTime
}
```

### JobSeekerProfile (Profile Details)

```typescript
{
  id: string (UUID)
  jobSeekerId: string (unique, FK to JobSeeker)
  title: string                    // Job title/position (e.g., "Software Engineer")
  cvEmail: string (unique)          // Email from CV
  phone: string                    // Phone number
  summary?: string                 // Professional summary (text)
  location?: string                // City, country
  availabilityStatus: AvailabilityStatusEnum  // OPEN_TO_WORK | NOT_LOOKING | PASSIVELY_LOOKING
  expectedSalary?: number          // Annual salary expectation
  workPreference: WorkPreferenceEnum          // ONSITE | REMOTE | HYBRID | ANY
  preferredJobTypes: JobTypeEnum[] // FULL_TIME | PART_TIME | CONTRACT | FREELANCE | INTERNSHIP
  yearsOfExperience?: number       // Total years of experience (float)
  noticePeriod?: number            // Notice period in days
  linkedinUrl?: string
  portfolioUrl?: string
  githubUrl?: string
  createdAt: DateTime
  updatedAt: DateTime
}
```

### Education

```typescript
{
  id: string (UUID)
  jobSeekerId: string (FK to JobSeeker)
  institutionName: string         // University/college name
  degreeType: DegreeTypeEnum       // HIGH_SCHOOL | ASSOCIATE | BACHELOR | MASTER | PHD | BOOTCAMP | CERTIFICATION | OTHER
  fieldOfStudy: string             // Major/program name
  startDate: Date                  // Start date
  endDate?: Date                   // End date (null if currently studying)
  gpa?: number                     // GPA (0-4 scale)
  isCurrent: boolean               // Currently studying here
  description?: string             // Additional details
  createdAt: DateTime
  updatedAt: DateTime
}
```

### WorkExperience

```typescript
{
  id: string (UUID)
  jobSeekerId: string (FK to JobSeeker)
  companyName: string              // Company name
  jobTitle: string                 // Position/job title
  location?: string                // Job location
  startDate: Date                  // Start date
  endDate?: Date                   // End date (null if current job)
  isCurrent: boolean               // Currently working here
  description?: string             // Job responsibilities/achievements
  createdAt: DateTime
  updatedAt: DateTime
}
```

### Skill

```typescript
{
  id: string (UUID)
  name: string (unique)             // Skill name (e.g., "Python", "React")
  aliases?: string[]                // Alternative names
  createdAt: DateTime
  updatedAt: DateTime
}
```

### JobSeekerSkill (Skill Association)

```typescript
{
  id: string (UUID)
  jobSeekerId: string (FK to JobSeeker)
  skillId: string (FK to Skill)
  verified: boolean (default: true) // Whether verified from CV
  createdAt: DateTime
  updatedAt: DateTime
}
```

### CV (CV File Reference)

```typescript
{
  id: string (UUID)
  jobSeekerId: string (unique, FK to JobSeeker)
  key: string                      // S3/MinIO object key
  fileName: string                 // Original filename
  mimeType: string                 // MIME type (application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document)
  uploadedAt: DateTime
}
```

---

## Enum Values

### DegreeTypeEnum

- `HIGH_SCHOOL`
- `ASSOCIATE`
- `BACHELOR`
- `MASTER`
- `PHD`
- `BOOTCAMP`
- `CERTIFICATION`
- `OTHER`

### JobTypeEnum

- `FULL_TIME`
- `PART_TIME`
- `CONTRACT`
- `FREELANCE`
- `INTERNSHIP`

### AvailabilityStatusEnum

- `OPEN_TO_WORK`
- `NOT_LOOKING`
- `PASSIVELY_LOOKING`

### WorkPreferenceEnum

- `ONSITE`
- `REMOTE`
- `HYBRID`
- `ANY`

---

## CV Parsing Requirements

### Input

- CV URL (presigned URL from storage)
- File types: PDF, DOCX

### Expected Output (JSON)

```json
{
  "personalInfo": {
    "firstName": "string",
    "lastName": "string",
    "email": "string",
    "phone": "string",
    "location": "string",
    "linkedinUrl": "string (optional)",
    "githubUrl": "string (optional)",
    "portfolioUrl": "string (optional)"
  },
  "professionalSummary": "string (optional)",
  "title": "string (desired position)",
  "education": [
    {
      "institutionName": "string",
      "degreeType": "HIGH_SCHOOL | ASSOCIATE | BACHELOR | MASTER | PHD | BOOTCAMP | CERTIFICATION | OTHER",
      "fieldOfStudy": "string",
      "startDate": "YYYY-MM-DD",
      "endDate": "YYYY-MM-DD (optional)",
      "isCurrent": boolean,
      "gpa": "number (optional)",
      "description": "string (optional)"
    }
  ],
  "workExperience": [
    {
      "companyName": "string",
      "jobTitle": "string",
      "location": "string (optional)",
      "startDate": "YYYY-MM-DD",
      "endDate": "YYYY-MM-DD (optional)",
      "isCurrent": boolean,
      "description": "string (optional)"
    }
  ],
  "skills": [
    {
      "name": "string (skill name)",
      "confidence": "number 0-1"
    }
  ],
  "expectedSalary": "number (optional, annual)",
  "workPreference": "ONSITE | REMOTE | HYBRID | ANY",
  "yearsOfExperience": "number (optional)",
  "noticePeriod": "number (optional, days)",
  "availabilityStatus": "OPEN_TO_WORK | NOT_LOOKING | PASSIVELY_LOOKING"
}
```

---

## Important Notes

1. **Skills Matching**: Extract skills should be matched against existing skills in the database. If a skill doesn't exist, return it with a flag to be created.

2. **Date Parsing**: Handle various date formats (MM/YYYY, YYYY, Month YYYY, etc.) and normalize to YYYY-MM-DD format.

3. **Multiple Educations**: A CV may contain multiple education entries. Return all of them.

4. **Multiple Work Experiences**: A CV may contain multiple work experiences. Return all in reverse chronological order.

5. **Current Positions**: Use present tense in job titles/dates to determine `isCurrent: true`.

6. **Confidence Scores**: Include confidence scores for extracted skills to help with verification.

7. **Language**: CVs may be in any language - extract as-is. Consider detecting language for future use.

---

## Integration Points

The Python service will interact with:

1. **Storage**: Download CV files from S3/MinIO presigned URLs
2. **Database**: Insert/update parsed data via API endpoints
3. **API Endpoints**:
   - `POST /job-seekers/me/cv` - Upload CV (get presigned URL)
   - `GET /job-seekers/me/cv` - Get CV info
   - `DELETE /job-seekers/me/cv` - Delete CV
   - `GET /job-seekers/me` - Get profile
   - `PATCH /job-seekers/me` - Update profile
   - `POST /job-seekers/me/education` - Add education
   - `PATCH /job-seekers/me/education/:id` - Update education
   - `DELETE /job-seekers/me/education/:id` - Delete education
   - `POST /job-seekers/me/work-experiences` - Add work experience
   - `PATCH /job-seekers/me/work-experiences/:id` - Update work experience
   - `DELETE /job-seekers/me/work-experiences/:id` - Delete work experience
   - `GET /skills` - Get all available skills (for matching)
   - `POST /job-seekers/me/skills` - Add skills to profile

---

## Error Handling

- Handle corrupted/unsupported CV files gracefully
- Handle network errors when downloading CVs
- Handle parsing failures with partial results where possible
- Return clear error messages for troubleshooting
