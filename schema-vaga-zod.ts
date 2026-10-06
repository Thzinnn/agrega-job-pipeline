.object({
    // Regra de Negócio: O título não pode ser malicioso ou vazio
    title: z.string({ required_error: 'Título da vaga é obrigatório' }).min(3, 'Título deve ter pelo menos 3 caracteres').max(120),
    company: z.string({ required_error: 'Nome da empresa é obrigatório' }).min(2, 'Empresa deve ter pelo menos 2 caracteres').max(100),
    description: z.string({ required_error: 'Descrição é obrigatória' }).min(10, 'Descrição deve ter pelo menos 10 caracteres'),
    location: z.string({ required_error: 'Localização é obrigatória' }).min(2, 'Localização deve ter pelo menos 2 caracteres').max(100),
    workplaceType: z.string(),
    education: z.preprocess((val) => (val === '' ? null : val), z.string().nullable().optional()),
    requirements: z.array(z.string().min(1, 'Requisito não pode ser vazio')).default([]).optional(),
    contractType: z.string().default('CLT'),
    benefits: z
      .string()
      .trim()
      .optional()
      .nullable()
      .transform((val) => (val && val.length > 0 ? val : null)),
    hasVA: z.boolean().default(false).optional(),
    hasVR: z.boolean().default(false).optional(),
    hasVT: z.boolean().default(false).optional(),
    hasLifeInsurance: z.boolean().default(false).optional(),
    hasMedicalInsurance: z.boolean().default(false).optional(),
    hasDentalInsurance: z.boolean().default(false).optional(),
    salary: z
      .preprocess(
        (val) => (val === '' || val === null || val === undefined ? null : Number(val)),
        z.number({ invalid_type_error: 'Salário deve ser um número' }).nonnegative('Salário não pode ser negativo').nullable().optional()
      ),
    salaryMin: z
      .preprocess(
        (val) => (val === '' || val === null || val === undefined ? null : Number(val)),
        z.number({ invalid_type_error: 'Salário mínimo deve ser um número' }).nonnegative('Salário mínimo não pode ser negativo').nullable().optional()
      ),
    salaryMax: z
      .preprocess(
        (val) => (val === '' || val === null || val === undefined ? null : Number(val)),
        z.number({ invalid_type_error: 'Salário máximo deve ser um número' }).nonnegative('Salário máximo não pode ser negativo').nullable().optional()
      ),
    // Segurança: Regex força links de candidatura legítimos, evitando injeções javascript:alert()
    applicationUrl: z
      .preprocess((val) => (val === '' ? undefined : val), z.string().url('Link de candidatura deve ser uma URL válida').regex(/^https?:\/\//i, 'O link deve obrigatoriamente iniciar com http:// ou https://').optional()),
    contactEmail: z
      .preprocess((val) => (val === '' ? undefined : val), z.string().email('E-mail inválido').optional()),
    contactPhone: z
      .preprocess((val) => (val === '' ? undefined : val), z.string().regex(/^[\d\s\-\+\(\)]+$/, 'Telefone inválido, use apenas números e os caracteres +, -, ()').optional()),
    source: z.string().default('MANUAL').optional(),
    isActive: z.boolean().default(true).optional(),
    customData: z.record(z.unknown()).optional(),
  });