function quant=invgen(Fchapeau,alpha)
%  PURPOSE:This function computes the generalized inversion of a discrete cdf function
%----------------- -----------------------------------------------------
%  USAGE: quant = invgen(Fchapeau,alpha)
%     where: Fchapeau = (n x 2) matrix where first column is ti and second column is F(ti)
%            alpha = order of the quantile (0 < alpha <=1)
%------------------- ---------------------------------------------------
%  OUTPUTS :  quant = antecedent
%-----------------------------------------------------------------------
% Eve Leconte, Christine Thomas-Agnan, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


i_max = length(Fchapeau(:,1));

if alpha > Fchapeau(i_max,2)

   quant = Fchapeau(i_max,1);

else

   i=1;

   while Fchapeau(i,2) < alpha

     i = i + 1;

   end

   quant = Fchapeau(i,1);

end