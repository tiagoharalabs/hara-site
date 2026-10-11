import assert from 'node:assert/strict';
import {
  APPROVED_COMMERCIAL_TERMS, stripeBillingConfigured,
  billingStatus, createBillingCheckout, createBillingPortal,
} from '../src/billing.mjs';

const tests=[];
const check=async(name,fn)=>{await fn();tests.push(name);};
const queries=[];
const env={
  ENVIRONMENT:'PROD',
  PRODUCT_DB:{
    prepare(sql){
      queries.push(sql);
      return {
        bind(...args){
          return {
            async first(){
              if(sql.includes('FROM plans')){
                if(args[0]==='STANDARD') return {
                  plan_code:'STANDARD',state:'ACTIVE',
                  display_name:'Pro',period_kind:'NONE',unit_limit:null,
                };
                return null;
              }
              if(sql.includes('FROM billing_connections')) return null;
              throw new Error('UNEXPECTED_BILLING_READ_QUERY');
            },
          };
        },
      };
    },
  },
};
const owner={role:'OWNER',tenant_id:'TENANT_FREE_TEST',subject_id:'SUBJECT_FREE_TEST'};
await check('no_stripe_credentials_is_not_configured',()=>assert.equal(stripeBillingConfigured(env),false));
const status=await billingStatus(env,owner);
await check('trial_owner_can_read_billing_catalog_without_stripe',()=>{
  assert.equal(status.schema,'hara.commander-billing-status.v1');
  assert.equal(status.can_manage,true);assert.equal(status.configured,false);
  assert.equal(status.secret_material_exposed,false);
});
await check('active_standard_still_displays_approved_terms',()=>{
  assert.equal(status.plans.STANDARD.catalog_active,true);
  assert.equal(status.plans.STANDARD.commercial_terms.price_display,'R$ 80');
  assert.equal(APPROVED_COMMERCIAL_TERMS.STANDARD.price_amount_cents,8000);
  assert.equal(status.plans.STANDARD.period_kind,'NONE');
  assert.equal(status.plans.STANDARD.unit_limit,null);
});
await check('standard_purchase_is_hidden_until_provider_ready',()=>{
  assert.equal(status.plans.STANDARD.price_configured,false);
  assert.equal(status.plans.STANDARD.checkout_ready,false);
  assert.equal(status.activation.first_checkout_ready,false);
  assert.equal(status.activation.provider_configured,false);
});
await check('no_connection_fabricated_without_payment',()=>assert.equal(status.connection,null));
await check('scale_cannot_be_accidentally_sold',()=>{
  assert.equal(status.plans.SCALE.checkout_ready,false);
  assert.equal(status.plans.SCALE.catalog_active,false);
});
let externalCalls=0;
const failFetch=()=>{externalCalls++;throw new Error('STRIPE_NETWORK_SHOULD_NOT_BE_CALLED');};
const request=new Request('https://commander.haralabs.com.br/api/portal/billing/checkout',{method:'POST'});
await check('checkout_fail_closed_before_external_request',async()=>{
 await assert.rejects(createBillingCheckout(request,env,owner,'STANDARD',failFetch),/BILLING_NOT_CONFIGURED/);
 assert.equal(externalCalls,0);
});
await check('customer_portal_fail_closed_without_credentials',async()=>{
 await assert.rejects(createBillingPortal(request,env,owner,failFetch),/BILLING_NOT_CONFIGURED/);
 assert.equal(externalCalls,0);
});
await check('member_cannot_checkout_even_in_unconfigured_state',async()=>{
 await assert.rejects(createBillingCheckout(request,env,{...owner,role:'MEMBER'},'STANDARD',failFetch),/BILLING_ADMIN_REQUIRED/);
 assert.equal(externalCalls,0);
});
await check('reviewer_cannot_manage_billing',async()=>{
 const review=await billingStatus(env,{...owner,role:'REVIEWER'});
 assert.equal(review.can_manage,false);
 assert.equal(review.activation.standard_checkout_ready,false);
});
await check('test_key_not_sufficient_for_prod',()=>{
 assert.equal(stripeBillingConfigured({...env,STRIPE_SECRET_KEY:'sk_test_FixtureOnly123456',STRIPE_WEBHOOK_SECRET:'whsec_FixtureOnly123456'}),false);
});
await check('partial_configuration_cannot_enable_checkout',async()=>{
 const partial={...env,STRIPE_PRICE_STANDARD:'price_SyntheticFixture'};
 const partialStatus=await billingStatus(partial,owner);
 assert.equal(partialStatus.plans.STANDARD.price_configured,true);
 assert.equal(partialStatus.plans.STANDARD.checkout_ready,false);
});
await check('no_mutating_product_db_query_was_issued',()=>{
 assert.ok(queries.length>0);
 assert.ok(queries.every(q=>/^\s*SELECT\b/i.test(q)),queries.join('\n'));
});
console.log(JSON.stringify({
 schema:'hara.commander-no-stripe-technical-mode.v1',
 checked:tests.length,passed:tests.length,failed:0,
 queries:queries.length,real_stripe_requests:externalCalls,
 runtime_secrets_required:false,production_mutation:false,
 checks:tests,
},null,2));
